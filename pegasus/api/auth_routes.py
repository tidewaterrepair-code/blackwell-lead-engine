"""Sign up, log in (password or magic link), log out, me, org settings, team."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..accounts import (
    AccountError,
    accept_invite,
    authenticate,
    invite,
    normalize_email,
    seat_count,
    signup,
    territory_allowance,
    touch_streak,
    award,
    validate_trades,
    mode_for,
)
from ..auth import make_token, read_token
from ..config import get_settings
from ..db import utcnow
from ..models import Invite, Membership, Org, OrgLead, Territory, User
from ..notify import send_invite, send_magic_link
from ..plans import effective_plan, public_catalog
from .deps import Ctx, csrf_guard, current_ctx, get_db, rate_limit, require_org_admin
from .serialize import iso, user_dict

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(csrf_guard)])
MAGIC_MAX_AGE = 30 * 60


class SignupIn(BaseModel):
    email: str
    password: str | None = None
    name: str | None = None
    org_name: str | None = None
    trades: list[str] = Field(default_factory=list)
    ref: str | None = None
    utm: dict = Field(default_factory=dict)
    invite: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class MagicIn(BaseModel):
    email: str


def _login(request: Request, user: User, org_id: int | None = None) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    if org_id:
        request.session["org"] = org_id


def me_payload(db: Session, ctx: Ctx) -> dict:
    org, plan = ctx.org, ctx.plan
    month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    leads_month = db.scalar(select(func.count()).select_from(OrgLead).where(
        OrgLead.org_id == org.id, OrgLead.created_at >= month_start)) or 0
    territories = db.scalar(select(func.count()).select_from(Territory).where(Territory.org_id == org.id)) or 0
    orgs = db.execute(select(Org.id, Org.name).join(Membership, Membership.org_id == Org.id)
                      .where(Membership.user_id == ctx.user.id)).all()
    return {
        "user": user_dict(ctx.user),
        "org": {
            "id": org.id, "name": org.name, "mode": org.mode, "trades": org.trades or [], "plan": org.plan,
            "plan_status": org.plan_status, "trial_ends_at": iso(org.trial_ends_at), "credits": org.credits or 0,
            "founding_member": org.founding_member, "referral_code": org.referral_code,
            "base_lat": org.base_lat, "base_lng": org.base_lng, "settings": org.settings or {},
            "role": ctx.membership.role, "has_billing": bool(org.stripe_customer_id),
        },
        "plan": {"key": plan.key, "label": plan.label, "features": sorted(plan.features), "trades": plan.trades,
                 "territories": territory_allowance(org), "seats": plan.seats, "monthly_credits": plan.monthly_credits,
                 "lead_delay_days": plan.lead_delay_days, "monthly_lead_cap": plan.monthly_lead_cap,
                 "max_radius_miles": plan.max_radius_miles},
        "usage": {"leads_this_month": leads_month, "territories": territories, "seats": seat_count(db, org)},
        "orgs": [{"id": i, "name": n} for i, n in orgs],
        "digest_hour": get_settings().digest_hour,
    }


@router.post("/api/auth/signup", dependencies=[Depends(rate_limit("signup", 10, 3600))])
def api_signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    inv = None
    if body.invite:
        data = read_token("invite", body.invite, 14 * 86400)
        inv = db.get(Invite, data["invite_id"]) if data else None
        if inv is None or inv.accepted_at:
            raise HTTPException(400, "That invite link is no longer valid.")
    try:
        if inv:
            user, _ = signup(db, email=body.email, password=body.password, name=body.name,
                             org_name=None, trades=[], utm=body.utm, create_org=False)
            accept_invite(db, inv, user)
            org_id = inv.org_id
        else:
            user, own_org = signup(db, email=body.email, password=body.password, name=body.name,
                                   org_name=body.org_name, trades=body.trades, ref=body.ref, utm=body.utm)
            org_id = own_org.id
    except AccountError as exc:
        raise HTTPException(400, str(exc)) from exc
    touch_streak(user)
    db.flush()
    _login(request, user, org_id)
    return {"ok": True, "org_id": org_id}


@router.post("/api/auth/login", dependencies=[Depends(rate_limit("login", 20, 900))])
def api_login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(400, "Email or password is incorrect.")
    _login(request, user)
    return {"ok": True}


@router.post("/api/auth/magic", dependencies=[Depends(rate_limit("magic", 5, 900))])
def api_magic(body: MagicIn, db: Session = Depends(get_db)):
    try:
        email = normalize_email(body.email)
    except AccountError as exc:
        raise HTTPException(400, str(exc)) from exc
    user = db.scalar(select(User).where(User.email == email))
    if user:  # same response either way, so this can't be used to probe for accounts
        token = make_token("magic", {"uid": user.id})
        try:
            send_magic_link(email, f"{get_settings().public_url}/auth/magic?token={token}")
        except Exception:  # noqa: BLE001 - a mail outage must not turn into an error page or leak who has an account
            log.exception("magic link to %s failed", email)
    return {"ok": True}


@router.get("/auth/magic")
def magic_landing(token: str, request: Request, db: Session = Depends(get_db)):
    data = read_token("magic", token, MAGIC_MAX_AGE)
    user = db.get(User, data["uid"]) if data else None
    if user is None:
        return RedirectResponse("/app/login?error=expired", status_code=303)
    user.email_verified_at = user.email_verified_at or utcnow()
    user.last_login_at = utcnow()
    _login(request, user)
    return RedirectResponse("/app", status_code=303)


@router.post("/api/auth/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
def api_me(request: Request, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if touch_streak(ctx.user):
        award(db, ctx.user, ctx.org.id, "daily_open")
    return me_payload(db, ctx)


class MeIn(BaseModel):
    name: str | None = None
    phone: str | None = None


@router.patch("/api/me")
def api_me_update(body: MeIn, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if body.name is not None:
        ctx.user.name = body.name.strip()[:200] or None
    if body.phone is not None:
        ctx.user.phone = body.phone.strip()[:40] or None
    return me_payload(db, ctx)


class OrgIn(BaseModel):
    name: str | None = None
    trades: list[str] | None = None
    base_lat: float | None = None
    base_lng: float | None = None
    settings: dict | None = None


ALLOWED_SETTINGS = {"digest", "alerts_min_score", "ntfy_topic", "monthly_goal", "company_phone", "brand_color",
                    "logo_url", "website", "onboarded"}


@router.patch("/api/org")
def api_org_update(body: OrgIn, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    org = ctx.org
    if body.name is not None and body.name.strip():
        org.name = body.name.strip()[:200]
    if body.trades is not None:
        try:
            org.trades = validate_trades(body.trades, effective_plan(org).trades)
        except AccountError as exc:
            raise HTTPException(400, str(exc)) from exc
        org.mode = mode_for(org.trades)
        from ..jobs import enqueue

        enqueue(db, "backfill_org", {"org_id": org.id}, unique_key=f"backfill:{org.id}")
    if body.base_lat is not None and body.base_lng is not None:
        org.base_lat, org.base_lng = body.base_lat, body.base_lng
    if body.settings:
        clean = {k: v for k, v in body.settings.items() if k in ALLOWED_SETTINGS}
        if clean.get("digest") is True:  # saving with Morning Drop on undoes this person's email opt-out
            clean["digest_muted"] = [u for u in (org.settings or {}).get("digest_muted", []) if u != ctx.user.id]
        org.settings = {**(org.settings or {}), **clean}
    return me_payload(db, ctx)


class SwitchIn(BaseModel):
    org_id: int


@router.post("/api/org/switch")
def api_switch(body: SwitchIn, request: Request, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    m = db.scalar(select(Membership).where(Membership.user_id == ctx.user.id, Membership.org_id == body.org_id))
    if m is None:
        raise HTTPException(404)
    request.session["org"] = body.org_id
    return {"ok": True}


@router.get("/api/team")
def api_team(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    members = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                         .where(Membership.org_id == ctx.org.id)).all()
    invites = db.scalars(select(Invite).where(Invite.org_id == ctx.org.id, Invite.accepted_at.is_(None))).all()
    return {
        "members": [{"id": m.id, "user_id": u.id, "email": u.email, "name": u.name, "role": m.role, "xp": u.xp,
                     "streak": u.streak_days} for m, u in members],
        "invites": [{"id": i.id, "email": i.email, "role": i.role, "created_at": iso(i.created_at)} for i in invites],
        "seats": {"used": seat_count(db, ctx.org), "limit": ctx.plan.seats},
    }


class InviteIn(BaseModel):
    email: str
    role: str = "member"


@router.post("/api/team/invite")
def api_invite(body: InviteIn, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    try:
        inv = invite(db, ctx.org, body.email, body.role)
    except AccountError as exc:
        raise HTTPException(400, str(exc)) from exc
    token = make_token("invite", {"invite_id": inv.id})
    send_invite(inv.email, ctx.org.name, f"{get_settings().public_url}/app/join?invite={token}")
    return {"ok": True, "id": inv.id}


@router.delete("/api/team/{membership_id}")
def api_remove_member(membership_id: int, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    m = db.get(Membership, membership_id)
    if m is None or m.org_id != ctx.org.id or m.role == "owner":
        raise HTTPException(404)
    db.delete(m)
    return {"ok": True}


@router.post("/api/team/accept")
def api_accept(body: dict, request: Request, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    data = read_token("invite", str(body.get("invite", "")), 14 * 86400)
    inv = db.get(Invite, data["invite_id"]) if data else None
    if inv is None or inv.accepted_at:
        raise HTTPException(400, "That invite link is no longer valid.")
    accept_invite(db, inv, ctx.user)
    request.session["org"] = inv.org_id
    return {"ok": True}


@router.get("/api/catalog")
def api_catalog():
    from ..intel.taxonomy import tags, trades
    from ..models import LEAD_STATUSES, SIGNAL_KINDS

    return {
        "trades": [{"key": t.key, "label": t.label, "group": t.group, "icon": t.icon, "ticket": t.ticket}
                   for t in trades().values()],
        "tags": {k: v.label for k, v in tags().items()},
        "kinds": SIGNAL_KINDS, "statuses": LEAD_STATUSES, "plans": public_catalog(),
    }


@router.get("/api/geo/search")
def api_geo_search(q: str):
    from ..geodata import search

    return {"results": search(q)}
