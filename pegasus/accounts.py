"""Accounts, orgs, territories, coverage and gamification."""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import hash_password, password_problem, referral_code, verify_password
from .config import get_settings
from .db import utcnow
from .geo import territory_bbox, validate_territory
from .geodata import ensure_jurisdiction, territory_counties
from .intel.taxonomy import trades as trade_defs
from .models import Event, Invite, Jurisdiction, Membership, Org, Referral, Source, Territory, User
from .plans import FOUNDING_SEATS, effective_plan, has_feature, start_trial

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


class AccountError(ValueError):
    """A user-facing validation problem."""


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AccountError("Enter a valid email address.")
    return email


def validate_trades(trades: list[str], limit: int | None = None) -> list[str]:
    known = trade_defs()
    clean = list(dict.fromkeys(t for t in trades or [] if t in known))
    if not clean:
        raise AccountError("Pick at least one trade.")
    if limit is not None and len(clean) > limit:
        raise AccountError(f"Your plan includes {limit} trade{'s' if limit != 1 else ''}. Upgrade to add more.")
    return clean


def mode_for(trades: list[str]) -> str:
    groups = {trade_defs()[t].group for t in trades}
    return "both" if groups == {"trades", "realestate"} else ("realestate" if groups == {"realestate"} else "trades")


def signup(session: Session, *, email: str, password: str | None, name: str | None, org_name: str | None,
           trades: list[str], ref: str | None = None, utm: dict | None = None,
           create_org: bool = True) -> tuple[User, Org | None]:
    email = normalize_email(email)
    if session.scalar(select(User).where(User.email == email)):
        raise AccountError("An account with that email already exists. Log in instead.")
    if password is not None:
        problem = password_problem(password)
        if problem:
            raise AccountError(problem)
    user = User(email=email, name=(name or "").strip() or None,
                password_hash=hash_password(password) if password else None,
                is_admin=email in get_settings().admin_emails, badges=[])
    if not create_org:  # joining an existing team through an invite
        session.add(user)
        session.flush()
        return user, None
    trades = validate_trades(trades)
    founding = session.scalar(select(func.count()).select_from(Org).where(Org.founding_member.is_(True))) or 0
    org = Org(name=(org_name or "").strip() or (name or email.split("@")[0]), trades=trades, mode=mode_for(trades),
              referral_code=_unique_code(session), founding_member=founding < FOUNDING_SEATS,
              settings={"digest": True, "alerts_min_score": 75}, utm=utm or {})
    start_trial(org)
    session.add_all([user, org])
    session.flush()
    session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    if ref:
        referrer = session.scalar(select(Org).where(Org.referral_code == ref.strip().lower()))
        if referrer and referrer.id != org.id:
            org.referred_by_org_id = referrer.id
            session.add(Referral(referrer_org_id=referrer.id, referred_org_id=org.id))
    track(session, org.id, user.id, "signup", {"trades": trades, "utm": utm or {}})
    session.flush()
    return user, org


def _unique_code(session: Session) -> str:
    while True:
        code = referral_code()
        if not session.scalar(select(Org.id).where(Org.referral_code == code)):
            return code


def authenticate(session: Session, email: str, password: str) -> User | None:
    try:
        email = normalize_email(email)
    except AccountError:
        return None
    user = session.scalar(select(User).where(User.email == email))
    if user and verify_password(password, user.password_hash):
        user.last_login_at = utcnow()
        return user
    return None


def primary_membership(session: Session, user: User, org_id: int | None = None) -> Membership | None:
    stmt = select(Membership).where(Membership.user_id == user.id)
    if org_id:
        stmt = stmt.where(Membership.org_id == org_id)
    return session.scalars(stmt.order_by(Membership.id)).first()


# ---------------------------------------------------------------- team

def seat_count(session: Session, org: Org) -> int:
    members = session.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org.id)) or 0
    pending = session.scalar(select(func.count()).select_from(Invite).where(Invite.org_id == org.id,
                                                                           Invite.accepted_at.is_(None))) or 0
    return members + pending


def invite(session: Session, org: Org, email: str, role: str = "member") -> Invite:
    email = normalize_email(email)
    if seat_count(session, org) >= effective_plan(org).seats:
        raise AccountError("All seats are in use. Upgrade for more seats.")
    inv = Invite(org_id=org.id, email=email, role=role if role in ("admin", "member") else "member")
    session.add(inv)
    session.flush()
    return inv


def accept_invite(session: Session, inv: Invite, user: User) -> Membership:
    existing = session.scalar(select(Membership).where(Membership.org_id == inv.org_id,
                                                       Membership.user_id == user.id))
    inv.accepted_at = utcnow()
    if existing:
        return existing
    m = Membership(org_id=inv.org_id, user_id=user.id, role=inv.role)
    session.add(m)
    session.flush()
    return m


# ---------------------------------------------------------------- territories

def territory_allowance(org: Org) -> int:
    return effective_plan(org).territories + int((org.settings or {}).get("extra_territories", 0))


def create_territory(session: Session, org: Org, *, kind: str, data: dict, name: str | None = None,
                     trades: list[str] | None = None, exclusive: bool = False) -> Territory:
    plan = effective_plan(org)
    try:
        data = validate_territory(kind, data)
    except (KeyError, TypeError, ValueError) as exc:
        raise AccountError(str(exc)) from exc
    count = session.scalar(select(func.count()).select_from(Territory).where(Territory.org_id == org.id)) or 0
    if count >= territory_allowance(org):
        raise AccountError(f"Your plan includes {territory_allowance(org)} area(s). Upgrade or add an area.")
    if kind == "radius" and data["miles"] > plan.max_radius_miles:
        raise AccountError(f"Your plan allows a radius up to {plan.max_radius_miles} miles.")
    if plan.key == "free" and kind not in ("zip", "radius"):
        raise AccountError("The free plan covers one ZIP code or a 10-mile radius.")
    if plan.key == "free" and kind == "zip" and len(data["zips"]) > 1:
        raise AccountError("The free plan covers one ZIP code.")
    trades = [t for t in (trades or []) if t in (org.trades or [])]
    if exclusive:
        if kind != "zip":
            raise AccountError("Exclusive territories are sold by ZIP code.")
        if not has_feature(org, "exclusive_territories"):
            slots = int((org.settings or {}).get("exclusive_slots", 0))
            used = sum(len(t.data.get("zips", [])) for t in session.scalars(
                select(Territory).where(Territory.org_id == org.id, Territory.exclusive.is_(True))))
            if used + len(data["zips"]) > slots:
                raise AccountError("Exclusive ZIPs are an add-on ($149/mo each). Buy one from Billing first.")
        for t in session.scalars(select(Territory).where(Territory.exclusive.is_(True), Territory.kind == "zip",
                                                         Territory.org_id != org.id)):
            other_org = session.get(Org, t.org_id)
            clash_trades = set(t.trades or (other_org.trades if other_org else [])) & set(trades or org.trades)
            clash_zips = set(t.data.get("zips", [])) & set(data["zips"])
            if clash_trades and clash_zips:
                raise AccountError(f"ZIP {sorted(clash_zips)[0]} is already exclusive for that trade.")
    terr = Territory(org_id=org.id, kind=kind, data=data, trades=trades, exclusive=exclusive,
                     name=(name or default_territory_name(kind, data))[:200])
    bbox = territory_bbox(kind, data)
    if bbox:
        terr.min_lat, terr.max_lat, terr.min_lng, terr.max_lng = bbox
    if kind == "radius" and org.base_lat is None:
        org.base_lat, org.base_lng = data["lat"], data["lng"]
    session.add(terr)
    session.flush()
    request_coverage(session, org, terr)
    from .jobs import enqueue

    enqueue(session, "backfill_org", {"org_id": org.id}, unique_key=f"backfill:{org.id}")
    track(session, org.id, None, "territory_created", {"kind": kind})
    return terr


def default_territory_name(kind: str, data: dict) -> str:
    from .geodata import county_label

    if kind == "radius":
        return f"{data.get('label') or 'Home base'} + {data['miles']:g} mi"
    if kind == "zip":
        zips = data["zips"]
        return f"ZIP {zips[0]}" if len(zips) == 1 else f"{len(zips)} ZIP codes"
    if kind == "county":
        names = [county_label(f) for f in data["fips"]]
        return names[0] if len(names) == 1 else f"{len(names)} counties"
    if kind == "city":
        return f"{data['city']}, {data['state']}".strip(", ")
    return "Custom area"


def request_coverage(session: Session, org: Org | None, terr: Territory) -> list[str]:
    """Make sure every county a territory touches is covered; queue Source Scout where it isn't."""
    from .jobs import enqueue

    queued = []
    for fips in sorted(territory_counties(terr.kind, terr.data)):
        try:
            j = ensure_jurisdiction(session, fips)
        except ValueError:
            continue
        has_sources = session.scalar(select(func.count()).select_from(Source).where(
            Source.jurisdiction_id == fips, Source.status == "active")) or 0
        if has_sources:
            j.coverage = "covered" if has_sources >= 2 else "partial"
            continue
        if j.coverage in ("none",) or (j.last_scouted_at and j.last_scouted_at < utcnow() - timedelta(days=30)):
            j.coverage = "scouting"
            enqueue(session, "scout_jurisdiction", {"fips": fips, "org_id": org.id if org else None},
                    unique_key=f"scout:{fips}")
            queued.append(fips)
    return queued


def coverage_report(session: Session, org: Org) -> list[dict]:
    out, seen = [], set()
    for terr in session.scalars(select(Territory).where(Territory.org_id == org.id)):
        for fips in sorted(territory_counties(terr.kind, terr.data)):
            if fips in seen:
                continue
            seen.add(fips)
            j = session.get(Jurisdiction, fips)
            sources = session.scalars(select(Source).where(Source.jurisdiction_id == fips)).all()
            out.append({
                "fips": fips, "name": j.name if j else fips, "coverage": j.coverage if j else "none",
                "sources": [{"id": s.id, "name": s.name, "kind": s.kind, "status": s.status} for s in sources],
            })
    return out


# ---------------------------------------------------------------- gamification

XP = {"lead_saved": 2, "lead_contacted": 10, "lead_quoted": 25, "lead_won": 100, "note": 3, "daily_open": 5,
      "skip_trace": 5, "share_recap": 20}
LEVELS = [0, 100, 300, 700, 1500, 3000, 6000, 12000, 25000]
BADGES = [
    ("first_contact", "First contact", lambda s: s["contacted"] >= 1),
    ("closer", "Closer: first win", lambda s: s["won"] >= 1),
    ("hat_trick", "Hat trick: 3 wins", lambda s: s["won"] >= 3),
    ("hustler", "Hustler: 25 contacts", lambda s: s["contacted"] >= 25),
    ("streak_7", "7-day streak", lambda s: s["streak"] >= 7),
    ("streak_30", "30-day streak", lambda s: s["streak"] >= 30),
    ("six_figures", "$100k won", lambda s: s["won_value"] >= 100_000),
]


def level_for(xp: int) -> dict:
    level = sum(1 for threshold in LEVELS if xp >= threshold)
    floor = LEVELS[level - 1]
    nxt = LEVELS[level] if level < len(LEVELS) else None
    return {"level": level, "xp": xp, "floor": floor, "next": nxt,
            "progress": round((xp - floor) / (nxt - floor), 3) if nxt else 1.0}


def touch_streak(user: User, today: date | None = None) -> bool:
    """Count consecutive active days. Returns True on the first activity of a new day."""
    today = today or utcnow().date()
    last = date.fromisoformat(user.last_active_on) if user.last_active_on else None
    if last == today:
        return False
    user.streak_days = (user.streak_days or 0) + 1 if last == today - timedelta(days=1) else 1
    user.last_active_on = today.isoformat()
    return True


def award(session: Session, user: User | None, org_id: int | None, action: str, props: dict | None = None
          ) -> list[str]:
    """Record an action, give XP and return newly earned badge names."""
    track(session, org_id, user.id if user else None, action, props or {})
    if user is None:
        return []
    user.xp = (user.xp or 0) + XP.get(action, 0)
    stats = user_stats(session, user, org_id)
    earned = []
    for key, label, test in BADGES:
        if key not in (user.badges or []) and test(stats):
            user.badges = [*(user.badges or []), key]
            earned.append(label)
    return earned


def user_stats(session: Session, user: User, org_id: int | None) -> dict:
    rows = dict(session.execute(select(Event.name, func.count()).where(Event.user_id == user.id)
                                .group_by(Event.name)).all())
    from .models import OrgLead

    won_value = 0.0
    if org_id:
        won_value = session.scalar(select(func.sum(OrgLead.value_won)).where(
            OrgLead.org_id == org_id, OrgLead.status == "won")) or 0.0
    return {"contacted": rows.get("lead_contacted", 0), "quoted": rows.get("lead_quoted", 0),
            "won": rows.get("lead_won", 0), "streak": user.streak_days or 0, "won_value": won_value}


def track(session: Session, org_id: int | None, user_id: int | None, name: str, props: dict | None = None) -> None:
    session.add(Event(org_id=org_id, user_id=user_id, name=name, props=props or {}))
