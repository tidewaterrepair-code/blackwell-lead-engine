"""Mission Control: platform-admin metrics, source health, Source Scout review queue, org management."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..jobs import enqueue
from ..models import (
    BillingEvent,
    Event,
    Job,
    Jurisdiction,
    Org,
    OrgLead,
    ScoutJob,
    Signal,
    Source,
    Territory,
    WaitlistSignup,
)
from ..plans import FOUNDING_DISCOUNT, PAID_PLANS, PLANS
from .deps import Ctx, csrf_guard, get_db, require_platform_admin
from .serialize import iso

router = APIRouter(dependencies=[Depends(csrf_guard), Depends(require_platform_admin)])


@router.get("/api/admin/overview")
def overview(db: Session = Depends(get_db)):
    now = utcnow()
    d30 = now - timedelta(days=30)
    orgs = db.scalars(select(Org)).all()
    paying = [o for o in orgs if o.plan in PAID_PLANS and o.plan_status in ("active", "past_due")
              and o.stripe_subscription_id]
    mrr = 0.0
    for o in paying:
        price = PLANS[o.plan].monthly * ((1 - FOUNDING_DISCOUNT) if o.founding_member else 1)
        if (o.settings or {}).get("interval") == "annual":
            price = PLANS[o.plan].annual / 12 * ((1 - FOUNDING_DISCOUNT) if o.founding_member else 1)
        mrr += price + 29 * int((o.settings or {}).get("extra_territories", 0)) \
            + 149 * int((o.settings or {}).get("exclusive_slots", 0))
    revenue_30d = (db.scalar(select(func.sum(BillingEvent.amount_cents)).where(
        BillingEvent.type == "invoice.paid", BillingEvent.created_at >= d30)) or 0) / 100
    churned = db.scalar(select(func.count()).select_from(BillingEvent).where(
        BillingEvent.type == "customer.subscription.deleted", BillingEvent.created_at >= d30)) or 0
    recent = [o for o in orgs if o.created_at >= d30]
    with_territory = set(db.scalars(select(Territory.org_id).distinct()))
    engaged = set(db.scalars(select(Event.org_id).where(Event.name.in_(("lead_contacted", "lead_quoted",
                                                                         "lead_won"))).distinct()))
    by_source = Counter((o.utm or {}).get("utm_source") or "direct" for o in recent)
    return {
        "mrr": round(mrr, 2), "arr": round(mrr * 12, 2), "revenue_30d": revenue_30d,
        "customers": {"total": len(orgs), "paying": len(paying),
                      "trialing": sum(1 for o in orgs if o.plan_status == "trialing"),
                      "free": sum(1 for o in orgs if o.plan == "free"), "churned_30d": churned,
                      "by_plan": dict(Counter(o.plan for o in paying)),
                      "founding_members": sum(1 for o in orgs if o.founding_member)},
        "funnel_30d": {"signups": len(recent), "set_area": sum(1 for o in recent if o.id in with_territory),
                       "worked_a_lead": sum(1 for o in recent if o.id in engaged),
                       "paying": sum(1 for o in recent if o in paying)},
        "signups_by_source_30d": dict(by_source.most_common()),
        "data": {
            "signals_24h": db.scalar(select(func.count()).select_from(Signal).where(Signal.created_at >= now - timedelta(days=1))),
            "signals_7d": db.scalar(select(func.count()).select_from(Signal).where(Signal.created_at >= now - timedelta(days=7))),
            "leads_7d": db.scalar(select(func.count()).select_from(OrgLead).where(OrgLead.created_at >= now - timedelta(days=7))),
            "jurisdictions": dict(db.execute(select(Jurisdiction.coverage, func.count()).group_by(Jurisdiction.coverage)).all()),
            "sources": dict(db.execute(select(Source.status, func.count()).group_by(Source.status)).all()),
        },
        "jobs": dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all()),
        "waitlist": db.scalar(select(func.count()).select_from(WaitlistSignup)),
    }


@router.get("/api/admin/sources")
def sources(db: Session = Depends(get_db)):
    rows = db.scalars(select(Source).order_by(Source.status, Source.id)).all()
    return {"items": [{"id": s.id, "name": s.name, "type": s.type, "kind": s.kind, "status": s.status,
                       "origin": s.origin, "jurisdiction": s.jurisdiction_id, "confidence": s.confidence,
                       "last_run_at": iso(s.last_run_at), "last_status": s.last_status, "last_error": s.last_error,
                       "last_fetched": s.last_fetched, "last_new": s.last_new,
                       "checks": (s.config or {}).get("scout_checks"), "sample": (s.config or {}).get("scout_sample"),
                       "url": (s.config or {}).get("scout_url")} for s in rows]}


class SourcePatch(BaseModel):
    status: str


@router.patch("/api/admin/sources/{source_id}")
def update_source(source_id: str, body: SourcePatch, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if src is None or body.status not in ("active", "disabled", "pending_review"):
        raise HTTPException(404)
    if body.status == "active" and src.status != "active":
        db.commit()
        from ..scout.runner import approve_source

        approve_source(source_id)
        return {"ok": True}
    src.status = body.status
    return {"ok": True}


@router.post("/api/admin/sources/{source_id}/run")
def run_source_now(source_id: str, db: Session = Depends(get_db)):
    if db.get(Source, source_id) is None:
        raise HTTPException(404)
    enqueue(db, "scrape_source", {"source_id": source_id}, unique_key=f"scrape:{source_id}")
    return {"queued": True}


@router.get("/api/admin/scout")
def scout_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(ScoutJob).order_by(ScoutJob.id.desc()).limit(50)).all()
    return {"items": [{"id": j.id, "jurisdiction": j.jurisdiction_id, "status": j.status, "log": j.log,
                       "candidates": j.candidates, "created_at": iso(j.created_at),
                       "finished_at": iso(j.finished_at)} for j in jobs]}


class ScoutIn(BaseModel):
    fips: str


@router.post("/api/admin/scout")
def scout_now(body: ScoutIn, db: Session = Depends(get_db)):
    enqueue(db, "scout_jurisdiction", {"fips": body.fips}, unique_key=f"scout:{body.fips}")
    return {"queued": True}


class PlanIn(BaseModel):
    plan: str
    status: str = "active"
    credits: int = 0


@router.post("/api/admin/orgs/{org_id}/plan")
def comp_plan(org_id: int, body: PlanIn, ctx: Ctx = Depends(require_platform_admin), db: Session = Depends(get_db)):
    from ..billing import add_credits

    org = db.get(Org, org_id)
    if org is None or body.plan not in PLANS:
        raise HTTPException(404)
    org.plan, org.plan_status = body.plan, body.status
    if body.credits:
        add_credits(db, org, body.credits, "admin_grant", f"user:{ctx.user.id}")
    return {"ok": True}


@router.get("/api/admin/orgs")
def list_orgs(db: Session = Depends(get_db), q: str | None = None):
    stmt = select(Org).order_by(Org.id.desc()).limit(200)
    if q:
        stmt = stmt.where(Org.name.ilike(f"%{q}%"))
    return {"items": [{"id": o.id, "name": o.name, "plan": o.plan, "status": o.plan_status, "trades": o.trades,
                       "credits": o.credits, "created_at": iso(o.created_at), "utm": o.utm} for o in db.scalars(stmt)]}


@router.get("/api/admin/waitlist")
def waitlist(db: Session = Depends(get_db)):
    rows = db.scalars(select(WaitlistSignup).order_by(WaitlistSignup.id.desc()).limit(1000)).all()
    return {"items": [{"email": w.email, "name": w.name, "audience": w.audience, "trade": w.trade, "city": w.city,
                       "utm": w.utm, "created_at": iso(w.created_at)} for w in rows]}
