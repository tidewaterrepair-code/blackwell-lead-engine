"""Leads: feed, detail, pipeline actions, notes, AI briefs, manual add, export, stats, live stream."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..accounts import award, touch_streak
from ..db import new_session, utcnow
from ..ingest import upsert_signal
from ..intel.ai import lead_brief, template_brief
from ..intel.predict import forecast
from ..intel.scoring import ScoreInput, score
from ..intel.taxonomy import tag_label, trades as trade_defs
from ..models import LEAD_STATUSES, OPEN_STATUSES, Activity, Contact, OrgLead, Prediction, Signal
from ..sources.base import LeadInput
from .deps import Ctx, csrf_guard, current_ctx, get_db
from .serialize import iso, lead_dict, signal_dict

router = APIRouter(dependencies=[Depends(csrf_guard)])

SORTS = {
    "score": lambda: [OrgLead.score.desc(), OrgLead.created_at.desc()],
    "newest": lambda: [OrgLead.created_at.desc()],
    "value": lambda: [Signal.est_value.desc().nulls_last(), OrgLead.score.desc()],
    "soonest": lambda: [Prediction.window_start.asc().nulls_last(), Signal.due_at.asc().nulls_last(),
                        OrgLead.score.desc()],
}


def lead_query(org_id: int, *, status: str = "open", lead_type: str | None = None, trade: str | None = None,
               tag: str | None = None, kind: str | None = None, q: str | None = None,
               min_score: int | None = None, days: int | None = None, city: str | None = None):
    stmt = (select(OrgLead).join(Signal, Signal.id == OrgLead.signal_id, isouter=True)
            .join(Prediction, Prediction.id == OrgLead.prediction_id, isouter=True)
            .where(OrgLead.org_id == org_id, OrgLead.visible_at <= utcnow()))
    if status == "open":
        stmt = stmt.where(OrgLead.status.in_(OPEN_STATUSES))
    elif status and status != "all":
        stmt = stmt.where(OrgLead.status == status)
    if lead_type:
        stmt = stmt.where(OrgLead.lead_type == lead_type)
    if trade:
        stmt = stmt.where(OrgLead.trade == trade)
    if tag:
        stmt = stmt.where(or_(Signal.primary_tag == tag, Prediction.tag == tag))
    if kind:
        stmt = stmt.where(Signal.kind == kind)
    if city:
        stmt = stmt.where(func.lower(Signal.city) == city.lower())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Signal.title.ilike(like), Signal.address.ilike(like), Signal.description.ilike(like),
                              Signal.contractor_name.ilike(like), Signal.owner_name.ilike(like)))
    if min_score:
        stmt = stmt.where(OrgLead.score >= min_score)
    if days:
        stmt = stmt.where(OrgLead.created_at >= utcnow() - timedelta(days=days))
    return stmt


@router.get("/api/leads")
def list_leads(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db), status: str = "open",
               type: str | None = None, trade: str | None = None, tag: str | None = None, kind: str | None = None,
               q: str | None = None, min_score: int | None = None, days: int | None = None, city: str | None = None,
               sort: str = "score", offset: int = 0, limit: int = Query(30, le=100)):
    stmt = lead_query(ctx.org.id, status=status, lead_type=type, trade=trade, tag=tag, kind=kind, q=q,
                      min_score=min_score, days=days, city=city)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = db.scalars(stmt.order_by(*SORTS.get(sort, SORTS["score"])()).offset(offset).limit(limit)).all()
    return {"items": [lead_dict(lead, ctx.org) for lead in items], "total": total,
            "next": offset + limit if offset + limit < total else None}


def _get_lead(db: Session, ctx: Ctx, lead_id: int) -> OrgLead:
    lead = db.get(OrgLead, lead_id)
    if lead is None or lead.org_id != ctx.org.id or lead.visible_at > utcnow():
        raise HTTPException(404, "Lead not found.")
    return lead


def _visible_signal(sig: Signal, org_id: int) -> bool:
    if sig.source_id.startswith("manual:") or sig.source_id.startswith("mls:"):
        return sig.source_id.split(":", 1)[1] == str(org_id)
    return True


@router.get("/api/leads/{lead_id}")
def lead_detail(lead_id: int, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    lead = _get_lead(db, ctx, lead_id)
    out = lead_dict(lead, ctx.org, full=True)
    sig = lead.signal
    locked = out["locked"]
    if sig and not locked:
        # Everything known about this address, newest first (the property's story).
        history = []
        if sig.property_id:
            for other in db.scalars(select(Signal).where(Signal.property_id == sig.property_id, Signal.id != sig.id)
                                    .order_by(Signal.created_at.desc()).limit(25)):
                if _visible_signal(other, ctx.org.id):
                    history.append(signal_dict(other))
        out["history"] = history
        # What happens next at this address, for every trade (the deep-logic timeline).
        anchor = sig.posted_at or sig.created_at
        out["next_jobs"] = [
            {"trade": f.trade, "trade_label": trade_defs()[f.trade].label, "tag_label": tag_label(f.tag),
             "window_start": iso(f.window_start), "window_end": iso(f.window_end), "probability": f.probability,
             "reason": f.reason, "yours": f.trade in (ctx.org.trades or [])}
            for f in forecast(sig.tags, sig.kind, anchor) if f.window_end >= utcnow()
        ] if ctx.feature("predictions") else []
        out["brief"] = (sig.data or {}).get("brief")
        out["contacts"] = [
            {"id": c.id, "name": c.name, "phones": c.phones, "emails": c.emails, "mailing_address": c.mailing_address,
             "created_at": iso(c.created_at)}
            for c in db.scalars(select(Contact).where(Contact.org_id == ctx.org.id,
                                                      or_(Contact.signal_id == sig.id,
                                                          and_(Contact.property_id.is_not(None),
                                                               Contact.property_id == sig.property_id))))
        ]
    out["activities"] = [{"id": a.id, "kind": a.kind, "body": a.body, "created_at": iso(a.created_at),
                          "user_id": a.user_id} for a in lead.activities]
    return out


class LeadPatch(BaseModel):
    status: str | None = None
    follow_up_at: datetime | None = None
    value_won: float | None = None
    assigned_user_id: int | None = None


STATUS_XP = {"saved": "lead_saved", "contacted": "lead_contacted", "quoted": "lead_quoted", "won": "lead_won"}


@router.patch("/api/leads/{lead_id}")
def update_lead(lead_id: int, body: LeadPatch, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    lead = _get_lead(db, ctx, lead_id)
    if lead.lead_type == "prediction" and not ctx.feature("predictions"):
        raise HTTPException(402, {"upgrade": True, "feature": "predictions"})
    badges: list[str] = []
    celebrate = False
    if body.status and body.status != lead.status:
        if body.status not in LEAD_STATUSES:
            raise HTTPException(400, "Unknown status.")
        db.add(Activity(org_lead_id=lead.id, user_id=ctx.user.id, kind="status",
                        body=f"{LEAD_STATUSES[lead.status]} → {LEAD_STATUSES[body.status]}"))
        lead.status = body.status
        if body.status in STATUS_XP:
            touch_streak(ctx.user)
            badges = award(db, ctx.user, ctx.org.id, STATUS_XP[body.status], {"lead_id": lead.id})
        celebrate = body.status == "won"
    if body.follow_up_at is not None:
        lead.follow_up_at = body.follow_up_at.replace(tzinfo=None)
    if body.value_won is not None:
        lead.value_won = max(0.0, body.value_won)
    if body.assigned_user_id is not None:
        lead.assigned_user_id = body.assigned_user_id or None
    db.flush()
    return {"lead": lead_dict(lead, ctx.org), "badges": badges, "celebrate": celebrate,
            "xp": ctx.user.xp, "streak": ctx.user.streak_days}


class NoteIn(BaseModel):
    body: str
    kind: str = "note"


@router.post("/api/leads/{lead_id}/notes")
def add_note(lead_id: int, body: NoteIn, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    lead = _get_lead(db, ctx, lead_id)
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Write something first.")
    act = Activity(org_lead_id=lead.id, user_id=ctx.user.id,
                   kind=body.kind if body.kind in ("note", "call", "quote", "email", "text") else "note", body=text[:5000])
    db.add(act)
    award(db, ctx.user, ctx.org.id, "note")
    db.flush()
    return {"id": act.id, "kind": act.kind, "body": act.body, "created_at": iso(act.created_at)}


@router.post("/api/leads/{lead_id}/brief")
def make_brief(lead_id: int, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    lead = _get_lead(db, ctx, lead_id)
    sig = lead.signal
    if sig is None or lead_dict(lead, ctx.org)["locked"]:
        raise HTTPException(402, {"upgrade": True, "feature": "predictions"})
    prop = sig.property
    audience = trade_defs()[lead.trade].group if lead.trade in trade_defs() else "trades"
    facts = {
        "title": sig.title, "kind": sig.kind, "job": tag_label(sig.primary_tag), "address": sig.address,
        "city": sig.city, "value": sig.est_value, "posted": iso(sig.posted_at), "description": sig.description,
        "contractor_listed": sig.contractor_name, "reasons": lead.reasons, "your_trade": lead.trade,
        "prediction": lead.prediction.reason if lead.prediction else None,
        "property": {"year_built": prop.year_built, "est_value": prop.est_value, "factors": (prop.data or {}).get("factors")}
        if prop else None,
    }
    cache_key = f"brief:{lead.trade}"
    cached = (sig.data or {}).get(cache_key)
    if cached:
        return cached
    brief = lead_brief(facts, audience) if ctx.feature("ai_briefs") else None
    result = {"source": "ai" if brief else "template", **(brief or template_brief(facts, audience))}
    sig.data = {**(sig.data or {}), cache_key: result}
    return result


class ManualIn(BaseModel):
    title: str
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    value: float | None = None
    url: str | None = None
    trade: str | None = None
    kind: str = "manual"


@router.post("/api/leads")
def add_manual(body: ManualIn, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(400, "Give the lead a short title.")
    item = LeadInput(external_id=uuid.uuid4().hex, kind=body.kind if body.kind in ("manual", "request") else "manual",
                     title=body.title.strip()[:480], description=body.description, address=body.address,
                     city=body.city, state=(body.state or "")[:2].upper() or None, zip=body.zip,
                     contact_name=body.contact_name, phone=body.phone, email=body.email, est_value=body.value,
                     url=body.url, posted_at=utcnow())
    sig, _ = upsert_signal(db, f"manual:{ctx.org.id}", item)
    trade = body.trade if body.trade in (ctx.org.trades or []) else (ctx.org.trades or [None])[0]
    tdef = trade_defs().get(trade or "")
    sc = score(ScoreInput(kind=sig.kind, est_value=sig.est_value, posted_at=sig.posted_at, lat=sig.lat, lng=sig.lng,
                          trade_group=tdef.group if tdef else "trades", default_ticket=tdef.ticket if tdef else None),
               base_lat=ctx.org.base_lat, base_lng=ctx.org.base_lng)
    lead = OrgLead(org_id=ctx.org.id, ref=f"s:{sig.id}", lead_type="signal", signal_id=sig.id, trade=trade,
                   score=max(sc.value, 50), reasons=["Added by you"], status="saved", visible_at=utcnow())
    db.add(lead)
    db.flush()
    return lead_dict(lead, ctx.org)


@router.get("/api/leads.csv")
def export_csv(request: Request, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if not ctx.feature("csv_export"):
        raise HTTPException(402, {"upgrade": True, "feature": "csv_export"})
    p = request.query_params
    stmt = lead_query(ctx.org.id, status=p.get("status", "all"), lead_type=p.get("type"), trade=p.get("trade"),
                      tag=p.get("tag"), q=p.get("q"))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "score", "status", "type", "trade", "job", "title", "address", "city", "state", "zip", "value",
                "contractor", "owner", "phone", "email", "posted", "window_start", "window_end", "url"])
    for lead in db.scalars(stmt.order_by(OrgLead.score.desc()).limit(20000)):
        d = lead_dict(lead, ctx.org, full=True)
        s, pr = d["signal"] or {}, d.get("prediction") or {}
        w.writerow([d["id"], d["score"], d["status"], d["type"], d["trade"], pr.get("tag_label") or s.get("tag_label"),
                    s.get("title"), s.get("address"), s.get("city"), s.get("state"), s.get("zip"), s.get("value"),
                    s.get("contractor"), s.get("owner_name"), s.get("phone"), s.get("email"), s.get("posted_at"),
                    pr.get("window_start"), pr.get("window_end"), s.get("url")])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=pegasus-leads.csv"})


@router.get("/api/stats")
def stats(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    now = utcnow()
    base = select(func.count()).select_from(OrgLead).where(OrgLead.org_id == ctx.org.id, OrgLead.visible_at <= now)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    won_month = db.scalar(select(func.sum(OrgLead.value_won)).where(
        OrgLead.org_id == ctx.org.id, OrgLead.status == "won", OrgLead.updated_at >= month_start)) or 0
    pipeline_value = db.scalar(select(func.sum(Signal.est_value)).join(OrgLead, OrgLead.signal_id == Signal.id).where(
        OrgLead.org_id == ctx.org.id, OrgLead.status.in_(("contacted", "quoted")),
        OrgLead.lead_type == "signal")) or 0
    by_tag = db.execute(
        select(Signal.primary_tag, func.count()).join(OrgLead, OrgLead.signal_id == Signal.id)
        .where(OrgLead.org_id == ctx.org.id, OrgLead.created_at >= now - timedelta(days=7), OrgLead.visible_at <= now)
        .group_by(Signal.primary_tag).order_by(func.count().desc()).limit(8)).all()
    by_status = dict(db.execute(select(OrgLead.status, func.count()).where(OrgLead.org_id == ctx.org.id)
                                .group_by(OrgLead.status)).all())
    from ..config import get_settings

    drop = now.replace(hour=get_settings().digest_hour, minute=0, second=0, microsecond=0)
    if drop <= now:
        drop += timedelta(days=1)
    return {
        "new_24h": db.scalar(base.where(OrgLead.created_at >= now - timedelta(hours=24))),
        "hot": db.scalar(base.where(OrgLead.status == "new", OrgLead.score >= 75)),
        "predicted": db.scalar(base.where(OrgLead.lead_type == "prediction", OrgLead.status.in_(OPEN_STATUSES))),
        "follow_ups_due": db.scalar(base.where(OrgLead.follow_up_at <= now, OrgLead.status.in_(OPEN_STATUSES))),
        "by_status": by_status, "won_this_month": won_month, "pipeline_value": pipeline_value,
        "monthly_goal": (ctx.org.settings or {}).get("monthly_goal"),
        "radar": [{"tag": t, "label": tag_label(t), "count": c} for t, c in by_tag],
        "next_drop_at": iso(drop), "credits": ctx.org.credits or 0,
    }


@router.get("/api/map")
def map_points(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db), status: str = "open",
               type: str | None = None, trade: str | None = None, days: int | None = 60, min_score: int | None = None):
    stmt = lead_query(ctx.org.id, status=status, lead_type=type, trade=trade, days=days, min_score=min_score
                      ).where(Signal.lat.is_not(None)).order_by(OrgLead.score.desc()).limit(1500)
    points = []
    for lead in db.scalars(stmt):
        d = lead_dict(lead, ctx.org)
        s = d["signal"]
        if not s or s["lat"] is None:
            continue
        points.append({"id": d["id"], "lat": s["lat"], "lng": s["lng"], "score": d["score"], "type": d["type"],
                       "tag": (d.get("prediction") or {}).get("tag") or s["tag"], "title": s["title"],
                       "status": d["status"]})
    return {"points": points}


@router.get("/api/recap")
def weekly_recap(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=7)
    leads = db.scalars(select(OrgLead).where(OrgLead.org_id == ctx.org.id, OrgLead.created_at >= since,
                                             OrgLead.visible_at <= utcnow())).all()
    value = sum((l.signal.est_value or 0) for l in leads if l.signal and l.lead_type == "signal")
    predicted = sum(1 for l in leads if l.lead_type == "prediction")
    won = db.scalar(select(func.sum(OrgLead.value_won)).where(OrgLead.org_id == ctx.org.id, OrgLead.status == "won",
                                                             OrgLead.updated_at >= since)) or 0
    return {"leads": len(leads), "value_found": value, "predicted": predicted, "won_value": won,
            "streak": ctx.user.streak_days or 0, "level": ctx.user.xp or 0,
            "share_text": f"Pegasus found {len(leads)} jobs (${value:,.0f}) in my area this week. 🐎⚡",
            "share_url": f"/r/{ctx.org.referral_code}"}


@router.post("/api/recap/share")
def share_recap(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    """Share-to-unlock: sharing the weekly recap earns 5 credits once per week."""
    from ..billing import add_credits

    week = utcnow().strftime("%G-W%V")
    if (ctx.org.settings or {}).get("last_share_week") == week:
        return {"credits": ctx.org.credits, "awarded": 0}
    add_credits(db, ctx.org, 5, "share_reward", week)
    ctx.org.settings = {**(ctx.org.settings or {}), "last_share_week": week}
    award(db, ctx.user, ctx.org.id, "share_recap")
    return {"credits": ctx.org.credits, "awarded": 5}


@router.get("/api/stream")
async def live_stream(request: Request, ctx: Ctx = Depends(current_ctx)):
    """Server-sent events: pushes new leads as they land (the live radar)."""
    org_id, org = ctx.org.id, ctx.org
    since = utcnow()

    async def events():
        nonlocal since
        yield "retry: 15000\n\n"
        while not await request.is_disconnected():
            session = new_session()
            try:
                fresh = session.scalars(select(OrgLead).where(
                    OrgLead.org_id == org_id, OrgLead.created_at > since, OrgLead.visible_at <= utcnow())
                    .order_by(OrgLead.created_at).limit(20)).all()
                for lead in fresh:
                    since = max(since, lead.created_at)
                    yield f"event: lead\ndata: {json.dumps(lead_dict(lead, org))}\n\n"
            finally:
                session.close()
            yield ": ping\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
