"""`pegasus marketing <action>`: render banners, export ads, check the calendar, build weekly posts."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path.cwd() / "marketing"


def check_calendar(path: Path) -> list[str]:
    problems = []
    with path.open() as f:
        rows = list(csv.DictReader(f))
    days = {int(r["day"]) for r in rows}
    if days != set(range(1, 31)):
        problems.append(f"calendar should cover days 1-30, has {sorted(days)[:3]}…")
    for i, r in enumerate(rows, start=2):
        if not r["hook"].strip() or not r["caption"].strip():
            problems.append(f"row {i}: missing hook or caption")
        if "X" in r["platforms"].split("+") and len(r["caption"]) > 280:
            problems.append(f"row {i}: X post over 280 characters")
    return problems


def render_emails(out: Path) -> list[Path]:
    """Every lifecycle/launch email as an HTML preview, plus the waitlist as a Listmonk import CSV."""
    import html
    import json

    from sqlalchemy import select

    from ..db import session_scope
    from ..lifecycle import base_values, render, sequences
    from ..models import EmailSuppression, User, WaitlistSignup

    out.mkdir(parents=True, exist_ok=True)
    written, index = [], []
    with session_scope() as s:
        values = {**base_values(s), "first_name": "Alex", "org_name": "Coastal Decks", "city": "Virginia Beach",
                  "trial_end": "June 14"}
        for name, seq in sequences().items():
            for e in seq["emails"]:
                subject, _text, body = render(e, values, "preview@example.com")
                path = out / f"{name}-{e['id']}.html"
                path.write_text(body)
                written.append(path)
                when = "broadcast" if seq["audience"] == "broadcast" else f"day {e['day']:+d} from {seq['anchor']}"
                index.append(f"<tr><td>{name}</td><td>{when}</td><td><a href='{path.name}'>"
                             f"{html.escape(subject)}</a></td></tr>")
        (out / "index.html").write_text("<meta charset=utf-8><style>body{font:14px Inter,sans-serif;padding:24px}"
                                        "td{padding:4px 12px}</style><h1>Pegasus emails</h1><table>"
                                        + "".join(index) + "</table>")
        suppressed = set(s.scalars(select(EmailSuppression.email)))
        accounts = {e.lower() for e in s.scalars(select(User.email))}
        with (out / "waitlist_listmonk.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["email", "name", "attributes"])
            for row in s.scalars(select(WaitlistSignup)):
                if row.email.lower() in suppressed:
                    continue
                w.writerow([row.email, row.name or "", json.dumps({
                    "audience": row.audience, "trade": row.trade, "city": row.city,
                    "has_account": row.email.lower() in accounts, **(row.utm or {})})])
    return written


def run(args) -> int:
    out = Path(args.out)
    action = args.action
    if action in ("ads", "all"):
        from .ads import export

        paths = export(ROOT / "ads" / "campaigns.yaml", out / "ads")
        print("ads:", ", ".join(str(p) for p in paths.values()))
    if action in ("calendar", "all"):
        problems = check_calendar(ROOT / "content" / "calendar.csv")
        print("calendar:", "OK (90 posts)" if not problems else "\n".join(problems))
        if problems:
            return 1
    if action in ("weekly-posts", "all"):
        from .weekly import write_weekly

        cities = [(args.city, args.state)] if args.city else [("Virginia Beach", "VA"), ("Norfolk", "VA"),
                                                             ("Chesapeake", "VA")]
        written = write_weekly(cities, out / "weekly", polish=True)
        print("weekly posts:", ", ".join(str(p) for p in written) or "no data this week")
    if action in ("brand", "all"):
        from .brand_pack import main as import_pack

        written = import_pack()
        print(f"brand: {len(written)} assets cut from marketing/brand/source")
    if action in ("emails", "all"):
        written = render_emails(out / "email")
        print(f"emails: {len(written)} previews + waitlist_listmonk.csv in {out / 'email'}")
    if action in ("render", "all"):
        from .banners import render_all

        written = render_all(ROOT / "banners" / "copy.yaml", out / "banners")
        print(f"banners: {len(written)} images in {out / 'banners'}")
        og = out / "banners" / "og-image-1200x630.png"
        if og.exists():
            import shutil

            shutil.copy(og, Path(__file__).resolve().parents[1] / "web" / "static" / "brand" / "og-image.png")
    return 0
