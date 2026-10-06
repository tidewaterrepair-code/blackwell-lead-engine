"""Command line: `leadengine <command>`.

  serve                 run the dashboard (uvicorn)
  worker                run the scheduler (ingest + digest on a timer)
  run [SOURCE ...]      ingest now (all enabled sources, or the ones named)
  inspect SOURCE        print a few raw records + how they normalize/classify
  sources               list configured sources and their last run
  digest                send the email digest now
  rescore               recompute all scores
  classify "TEXT"       test the classifier on a description
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta

from .config import get_settings, load_sources


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_run(args) -> int:
    from .db import utcnow
    from .notify import push_hot_leads
    from .pipeline import run_all, run_source

    since = utcnow() - timedelta(days=args.days) if args.days else None
    if args.dry_run:
        sources = load_sources()
        for sid in args.sources or [k for k, v in sources.items() if v.get("enabled")]:
            res = run_source(sid, sources[sid], since=since, dry_run=True)
            print(f"{sid}: fetched={res.fetched} would_add={res.new_leads} skipped={res.skipped} error={res.error}")
        return 0
    results = run_all(args.sources or None, since=since)
    for r in results:
        print(f"{r.source_id}: fetched={r.fetched} new={r.new_leads} updated={r.updated_leads} "
              f"skipped={r.skipped}{' ERROR ' + r.error if r.error else ''}")
    push_hot_leads()
    return 1 if any(r.error for r in results) else 0


def cmd_inspect(args) -> int:
    from .classify import classify
    from .db import utcnow
    from .sources import build_adapter

    sources = load_sources()
    if args.source not in sources:
        print(f"unknown source {args.source!r}; configured: {', '.join(sources)}", file=sys.stderr)
        return 2
    adapter = build_adapter(args.source, sources[args.source])
    if hasattr(adapter, "sample") and not args.days:
        rows = adapter.sample(args.limit)
        print(f"--- {len(rows)} raw rows (columns: {sorted(rows[0]) if rows else []})")
        payloads = rows
    else:
        payloads = []
        for raw in adapter.fetch(utcnow() - timedelta(days=args.days or 7)):
            payloads.append(raw.payload)
            if len(payloads) >= args.limit:
                break
    for payload in payloads:
        print("\nRAW:", json.dumps(payload, default=str)[:1500])
        item = adapter.normalize(payload)
        if item is None:
            print("  -> skipped by normalize()")
            continue
        c = classify(kind=item.kind, title=item.title, description=item.description,
                     permit_type=item.permit_type, contractor_name=item.contractor_name, hints=item.hints)
        print(f"  -> {item.title!r} | {item.address} | value={item.est_value} | posted={item.posted_at}")
        print(f"     job_type={c.job_type} customer={c.customer_type} relevant={c.relevant} matched={c.matched}")
    return 0


def cmd_sources(_args) -> int:
    from .db import Source, session_scope

    with session_scope() as session:
        for sid, cfg in load_sources().items():
            src = session.get(Source, sid)
            last = f"{src.last_status} @ {src.last_run_at:%Y-%m-%d %H:%M} new={src.last_new_leads}" if src and src.last_run_at else "never run"
            print(f"{'ON ' if cfg.get('enabled') else 'off'} {sid:28} {cfg.get('type'):11} {last}")
    return 0


def cmd_classify(args) -> int:
    from .classify import classify

    c = classify(kind=args.kind, title=args.text, permit_type=args.permit_type)
    print(json.dumps(c.__dict__, indent=2))
    return 0


def cmd_digest(_args) -> int:
    from .notify import send_digest

    print(f"digest leads: {send_digest()}")
    return 0


def cmd_rescore(_args) -> int:
    from .pipeline import rescore_all

    print(f"rescored {rescore_all()} leads")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("leadengine.web.app:app", host=args.host, port=args.port, proxy_headers=True,
                forwarded_allow_ips="*")
    return 0


def cmd_worker(_args) -> int:
    from .worker import main as worker_main

    worker_main()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leadengine", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="ingest now")
    p.add_argument("sources", nargs="*")
    p.add_argument("--days", type=int, help="look back this many days instead of since last run")
    p.add_argument("--dry-run", action="store_true", help="fetch and classify without saving")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("inspect", help="show raw records and how they classify")
    p.add_argument("source")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--days", type=int, help="use fetch() over this many days instead of a raw sample")
    p.set_defaults(func=cmd_inspect)

    sub.add_parser("sources", help="list sources").set_defaults(func=cmd_sources)
    sub.add_parser("digest", help="send email digest now").set_defaults(func=cmd_digest)
    sub.add_parser("rescore", help="recompute scores").set_defaults(func=cmd_rescore)

    p = sub.add_parser("classify", help="test the classifier")
    p.add_argument("text")
    p.add_argument("--kind", default="permit")
    p.add_argument("--permit-type")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("serve", help="run the dashboard")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    sub.add_parser("worker", help="run the scheduler").set_defaults(func=cmd_worker)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    get_settings()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
