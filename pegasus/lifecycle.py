"""Lifecycle email: waitlist nurture, onboarding, trial-to-paid and win-back sequences.

Copy lives in pegasus/marketing/emails/*.yaml. The daily job calls run_lifecycle(); each email
is sent once, inside a 3-day window after it falls due (so turning this on never blasts a
backlog), never to suppressed addresses, and with a one-click unsubscribe link.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import make_token, read_token
from .config import get_settings
from .db import utcnow
from .models import EmailSuppression, Membership, Org, OrgLead, Territory, User, WaitlistSignup
from .notify import send_email, wrap_html
from .plans import FOUNDING_SEATS

log = logging.getLogger(__name__)
EMAIL_DIR = Path(__file__).parent / "marketing" / "emails"
SEND_WINDOW = timedelta(days=3)
UNSUB_PURPOSE = "unsubscribe"


@lru_cache(maxsize=1)
def sequences() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(EMAIL_DIR.glob("*.yaml"))}


def unsubscribe_url(email: str) -> str:
    return f"{get_settings().public_url}/email/unsubscribe?t={make_token(UNSUB_PURPOSE, {'e': email.lower()})}"


def read_unsubscribe_token(token: str) -> str | None:
    data = read_token(UNSUB_PURPOSE, token, max_age=60 * 60 * 24 * 365 * 3) if token else None
    return (data or {}).get("e")


class _Vars(dict):
    def __missing__(self, key):  # unknown placeholders render empty rather than crash a send
        return ""


def fill(text: str, values: dict) -> str:
    return text.format_map(_Vars(values))


def body_html(text: str) -> str:
    """Tiny markdown subset: blank-line paragraphs and '- ' bullet lists."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if all(ln.lstrip().startswith("- ") for ln in lines):
            items = "".join(f"<li style='margin:4px 0'>{html.escape(ln.lstrip()[2:])}</li>" for ln in lines)
            out.append(f"<ul style='padding-left:20px;margin:0 0 14px'>{items}</ul>")
        else:
            out.append(f"<p style='margin:0 0 14px'>{html.escape(' '.join(ln.strip() for ln in lines))}</p>")
    return "".join(out)


def render(email: dict, values: dict, to: str) -> tuple[str, str, str]:
    """Return (subject, text, html) for one email."""
    subject = fill(email["subject"], values)
    body = fill(email["body"], values)
    cta_label, cta_url = (fill(x, values) for x in email.get("cta") or ("", ""))
    unsub = unsubscribe_url(to)
    preview = html.escape(fill(email.get("preview", ""), values))
    footer = (f"Pegasus · data &amp; lead technology · <a href='{html.escape(unsub)}' style='color:#807058'>"
              "Unsubscribe</a>")
    hidden = f"<div style='display:none;max-height:0;overflow:hidden'>{preview}</div>"
    html_body = hidden + wrap_html(subject, body_html(body), cta_label or None, cta_url or None, footer)
    text = f"{body.strip()}\n\n{cta_label}: {cta_url}\n\n--\nUnsubscribe: {unsub}\n"
    return subject, text, html_body


def base_values(session: Session) -> dict:
    s = get_settings()
    founding = session.scalar(select(func.count()).select_from(Org).where(Org.founding_member.is_(True))) or 0
    return {"site_url": s.public_url, "app_url": f"{s.public_url}/app", "signup_url": f"{s.public_url}/app/signup",
            "pricing_url": f"{s.public_url}/app/billing", "founding_left": max(0, FOUNDING_SEATS - founding),
            "city_url": f"{s.public_url}/leads"}


def _first_name(name: str | None, email: str) -> str:
    return (name or "").split(" ")[0] or "there"


def _parse(dt) -> datetime | None:
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    if isinstance(dt, str) and dt:
        return datetime.fromisoformat(dt).replace(tzinfo=None)
    return None


def _due(anchor: datetime | None, day: int, now: datetime) -> bool:
    if anchor is None:
        return False
    at = anchor + timedelta(days=day)
    return at <= now < at + SEND_WINDOW


def _org_facts(session: Session, org: Org) -> dict[str, bool]:
    return {
        "paid": bool(org.stripe_subscription_id) and org.plan_status in ("active", "past_due"),
        "has_territory": bool(session.scalar(select(func.count()).select_from(Territory)
                                             .where(Territory.org_id == org.id))),
        "has_contacted": bool(session.scalar(select(func.count()).select_from(OrgLead).where(
            OrgLead.org_id == org.id, OrgLead.status.in_(("contacted", "quoted", "won", "lost"))))),
        "mode_realestate": org.mode in ("realestate", "both"),
        "mode_trades": org.mode in ("trades", "both"),
    }


def _anchor(org: Org, name: str) -> datetime | None:
    if name == "canceled_at":
        return _parse((org.settings or {}).get("canceled_at"))
    return _parse(getattr(org, name))


def _owner(session: Session, org: Org) -> User | None:
    return session.scalar(select(User).join(Membership, Membership.user_id == User.id)
                          .where(Membership.org_id == org.id).order_by(
                              (Membership.role != "owner"), Membership.id).limit(1))


def run_lifecycle(session: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    suppressed = {e for (e,) in session.execute(select(EmailSuppression.email))}
    base = base_values(session)
    sent = 0
    seqs = sequences()

    # Waitlist (no account yet)
    account_emails = {e.lower() for (e,) in session.execute(select(User.email))}
    for w in session.scalars(select(WaitlistSignup).where(WaitlistSignup.created_at >= now - timedelta(days=30))):
        email = w.email.lower()
        if email in suppressed or email in account_emails:
            continue
        values = {**base, "first_name": _first_name(w.name, email), "city": w.city or "your area"}
        for seq in (q for q in seqs.values() if q["audience"] == "waitlist"):
            for e in seq["emails"]:
                if e["id"] in (w.emails_sent or []) or not _due(_parse(w.created_at), e["day"], now):
                    continue
                if _send(email, e, values):
                    w.emails_sent = [*(w.emails_sent or []), e["id"]]
                    sent += 1

    # Accounts
    for org in session.scalars(select(Org)):
        owner = _owner(session, org)
        if owner is None or owner.email.lower() in suppressed:
            continue
        if (org.settings or {}).get("lifecycle_emails") is False:
            continue
        facts = None
        done = set((org.settings or {}).get("emails_sent", []))
        trial_end = _parse(org.trial_ends_at)
        values = {**base, "first_name": _first_name(owner.name, owner.email), "org_name": org.name,
                  "trial_end": f"{trial_end:%B} {trial_end.day}" if trial_end else "the end of your trial"}
        for seq in (q for q in seqs.values() if q["audience"] == "org"):
            anchor = _anchor(org, seq["anchor"])
            for e in seq["emails"]:
                if e["id"] in done or not _due(anchor, e["day"], now):
                    continue
                facts = facts or _org_facts(session, org)
                if any(facts.get(c) for c in seq.get("stop_if", []) + e.get("skip_if", [])):
                    continue
                if not all(facts.get(c) for c in e.get("only_if", [])):
                    continue
                if _send(owner.email, e, values):
                    done.add(e["id"])
                    sent += 1
        if done != set((org.settings or {}).get("emails_sent", [])):
            org.settings = {**(org.settings or {}), "emails_sent": sorted(done)}
    return sent


def _send(to: str, email: dict, values: dict) -> bool:
    subject, text, html_body = render(email, values, to)
    unsub = unsubscribe_url(to)
    try:
        send_email(to, subject, text, html_body, headers={
            "List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
    except Exception:  # noqa: BLE001 - one bad address must not stop the batch
        log.exception("lifecycle email %s to %s failed", email["id"], to)
        return False
    return True
