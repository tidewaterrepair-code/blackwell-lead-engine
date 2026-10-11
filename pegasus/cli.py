"""Command line: `pegasus <command>`.

  serve                  run the web app (API + app + marketing site)
  worker                 run background jobs + the schedule
  db upgrade             apply database migrations (production Postgres)
  run [SOURCE ...]       ingest now (all active sources, or the ones named)
  inspect SOURCE         print raw records and how they normalize/classify
  sources                list sources and their health
  scout FIPS             discover data sources for a county (Source Scout)
  approve SOURCE         approve a Scout-proposed source
  classify "TEXT"        test the classifier
  make-admin EMAIL       give a user platform-admin (Mission Control) access
  daily                  run the daily job now (rescore, digests, learning)
  demo                   seed demo data + demo accounts (dev/staging only)
  marketing ...          launch toolkit (banners, ads, calendar, weekly posts, emails)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta

from .config import get_settings


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_run(args) -> int:
    from .db import session_scope, utcnow
    from .ingest import run_all, run_source, sync_seed_sources

    with session_scope() as s:
        sync_seed_sources(s)
    since = utcnow() - timedelta(days=args.days) if args.days else None
    if args.dry_run:
        for sid in args.sources:
            res = run_source(sid, since=since, dry_run=True)
            print(f"{sid}: fetched={res.fetched} would_add={res.new_signals} skipped={res.skipped} error={res.error}")
        return 0
    results = run_all(args.sources or None, since=since)
    for r in results:
        print(f"{r.source_id}: fetched={r.fetched} new={r.new_signals} updated={r.updated_signals} "
              f"skipped={r.skipped} org_leads={r.org_leads}{' ERROR ' + r.error if r.error else ''}")
    return 1 if any(r.error for r in results) else 0


def cmd_inspect(args) -> int:
    from .db import session_scope, utcnow
    from .ingest import classify_item, sync_seed_sources
    from .models import Source
    from .sources import build_adapter

    with session_scope() as s:
        sync_seed_sources(s)
        src = s.get(Source, args.source)
        if src is None:
            print(f"unknown source {args.source!r}", file=sys.stderr)
            return 2
        config = {**src.config, "type": src.type, "kind": src.kind}
    adapter = build_adapter(args.source, config)
    if hasattr(adapter, "sample") and not args.days:
        payloads = adapter.sample(args.limit)
        print(f"--- {len(payloads)} raw rows; columns: {sorted(payloads[0]) if payloads else []}")
    else:
        payloads = []
        for raw in adapter.fetch(utcnow() - timedelta(days=args.days or 7)):
            payloads.append(raw.payload)
            if len(payloads) >= args.limit:
                break
    for payload in payloads:
        print("\nRAW:", json.dumps(payload, default=str)[:1500])
        item = adapter.apply_defaults(adapter.normalize(payload))
        if item is None:
            print("  -> skipped by normalize()")
            continue
        c = classify_item(item)
        print(f"  -> [{item.kind}] {item.title!r} | {item.address} | {item.city} {item.zip} | value={item.est_value} "
              f"| posted={item.posted_at}")
        print(f"     tags={c.tags} customer={c.customer_type} relevant={c.relevant} facts={item.facts}")
    return 0


def cmd_sources(_args) -> int:
    from sqlalchemy import select

    from .db import session_scope
    from .ingest import sync_seed_sources
    from .models import Source

    with session_scope() as s:
        sync_seed_sources(s)
        for src in s.scalars(select(Source).order_by(Source.status, Source.id)):
            last = f"{src.last_status} @ {src.last_run_at:%Y-%m-%d %H:%M} new={src.last_new}" if src.last_run_at else "never run"
            print(f"{src.status:15} {src.id:40} {src.type:10} {src.kind:14} {last}")
    return 0


def cmd_scout(args) -> int:
    from .scout.runner import scout

    print(json.dumps(scout(args.fips), indent=2))
    return 0


def cmd_approve(args) -> int:
    from .scout.runner import approve_source

    approve_source(args.source)
    print(f"approved {args.source}")
    return 0


def cmd_classify(args) -> int:
    from .intel.classify import classify

    c = classify(kind=args.kind, title=args.text, permit_type=args.permit_type)
    print(json.dumps(c.__dict__, indent=2))
    return 0


def cmd_make_admin(args) -> int:
    from sqlalchemy import select

    from .db import session_scope
    from .models import User

    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            print("no such user; sign up first", file=sys.stderr)
            return 2
        user.is_admin = True
    print(f"{args.email} is now a platform admin")
    return 0


def cmd_daily(_args) -> int:
    from .tasks import daily

    print(json.dumps(daily({}), indent=2, default=str))
    return 0


def cmd_db(args) -> int:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    if args.action == "upgrade":
        command.upgrade(cfg, "head")
    elif args.action == "revision":
        command.revision(cfg, message=args.message or "change", autogenerate=True)
    elif args.action == "stamp":  # a database created before migrations existed: mark it current
        command.stamp(cfg, "head")
    elif args.action == "current":
        command.current(cfg, verbose=True)
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("pegasus.web.app:app", host=args.host, port=args.port, proxy_headers=True, forwarded_allow_ips="*",
                workers=args.workers)
    return 0


def cmd_worker(args) -> int:
    from .worker import main as worker_main

    worker_main(args.threads)
    return 0


def cmd_demo(_args) -> int:
    from .demo import seed

    print(json.dumps(seed(), indent=2))
    return 0


def cmd_marketing(args) -> int:
    from .marketing.cli import run

    return run(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pegasus", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="ingest now")
    p.add_argument("sources", nargs="*")
    p.add_argument("--days", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("inspect", help="show raw records and how they classify")
    p.add_argument("source")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--days", type=int)
    p.set_defaults(func=cmd_inspect)

    sub.add_parser("sources", help="list sources").set_defaults(func=cmd_sources)
    p = sub.add_parser("scout", help="discover sources for a county FIPS code")
    p.add_argument("fips")
    p.set_defaults(func=cmd_scout)
    p = sub.add_parser("approve", help="approve a proposed source")
    p.add_argument("source")
    p.set_defaults(func=cmd_approve)
    p = sub.add_parser("classify", help="test the classifier")
    p.add_argument("text")
    p.add_argument("--kind", default="permit")
    p.add_argument("--permit-type")
    p.set_defaults(func=cmd_classify)
    p = sub.add_parser("make-admin", help="grant Mission Control access")
    p.add_argument("email")
    p.set_defaults(func=cmd_make_admin)
    sub.add_parser("daily", help="run the daily job now").set_defaults(func=cmd_daily)
    sub.add_parser("demo", help="seed demo data and accounts (dev only)").set_defaults(func=cmd_demo)
    p = sub.add_parser("db", help="database migrations")
    p.add_argument("action", choices=["upgrade", "revision", "stamp", "current"])
    p.add_argument("-m", "--message")
    p.set_defaults(func=cmd_db)
    p = sub.add_parser("serve", help="run the web app")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--workers", type=int, default=1)
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("worker", help="run background jobs")
    p.add_argument("--threads", type=int, default=3)
    p.set_defaults(func=cmd_worker)
    p = sub.add_parser("marketing", help="launch toolkit")
    p.add_argument("action", choices=["render", "ads", "calendar", "weekly-posts", "emails", "all"])
    p.add_argument("--out", default="marketing/dist")
    p.add_argument("--city")
    p.add_argument("--state", default="VA")
    p.set_defaults(func=cmd_marketing)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    get_settings()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
