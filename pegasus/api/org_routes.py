"""Territories & coverage, real estate (deals, analyzer, skip trace, MLS, farm, reports), billing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..accounts import AccountError, award, coverage_report, create_territory
from ..auth import encrypt_secret
from ..billing import BillingError, InsufficientCredits, checkout_url, handle_webhook, portal_url
from ..config import get_settings
from ..models import Contact, CreditLedger, Listing, MLSConnection, OrgLead, Property, Referral, Signal, Territory
from ..plans import CREDIT_PACKS, EXCLUSIVE_ZIP_PRICE, EXTRA_TERRITORY_PRICE, public_catalog
from ..realestate.deals import analyze
from ..realestate.farm import farm_stats
from ..realestate.skiptrace import SkipTraceError, skip_trace
from .deps import Ctx, csrf_guard, current_ctx, get_db, require_feature, require_org_admin
from .serialize import iso, lead_dict, property_dict, territory_dict

router = APIRouter(dependencies=[Depends(csrf_guard)])
public = APIRouter()


# ---------------------------------------------------------------- territories

class TerritoryIn(BaseModel):
    kind: str
    data: dict
    name: str | None = None
    trades: list[str] = Field(default_factory=list)
    exclusive: bool = False


@router.get("/api/territories")
def list_territories(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    items = db.scalars(select(Territory).where(Territory.org_id == ctx.org.id).order_by(Territory.id)).all()
    return {"items": [territory_dict(t) for t in items], "coverage": coverage_report(db, ctx.org)}


@router.post("/api/territories")
def add_territory(body: TerritoryIn, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    try:
        terr = create_territory(db, ctx.org, kind=body.kind, data=body.data, name=body.name, trades=body.trades,
                                exclusive=body.exclusive)
    except AccountError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"territory": territory_dict(terr), "coverage": coverage_report(db, ctx.org)}


@router.delete("/api/territories/{territory_id}")
def delete_territory(territory_id: int, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    terr = db.get(Territory, territory_id)
    if terr is None or terr.org_id != ctx.org.id:
        raise HTTPException(404)
    db.delete(terr)
    return {"ok": True}


# ---------------------------------------------------------------- real estate

@router.get("/api/deals")
def deal_radar(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db), min_motivation: int = 0,
               distress: str | None = None, sort: str = "motivation", limit: int = 60, offset: int = 0):
    """Properties behind the org's real estate leads, ranked by motivation or likelihood to sell."""
    stmt = (select(OrgLead, Property).join(Signal, Signal.id == OrgLead.signal_id, isouter=True)
            .join(Property, Property.id == func.coalesce(OrgLead.property_id, Signal.property_id))
            .where(OrgLead.org_id == ctx.org.id, OrgLead.status.in_(("new", "saved", "contacted", "quoted")),
                   Property.motivation_score >= min_motivation))
    order = Property.sell_probability.desc() if sort == "sell" else Property.motivation_score.desc()
    rows = db.execute(stmt.order_by(order, OrgLead.score.desc()).offset(offset).limit(limit * 3)).all()
    seen, items = set(), []
    for lead, prop in rows:
        if prop.id in seen or (distress and distress not in (prop.distress or [])):
            continue
        seen.add(prop.id)
        items.append({"lead": lead_dict(lead, ctx.org), "property": property_dict(prop)})
        if len(items) >= limit:
            break
    return {"items": items, "likely_to_sell": ctx.feature("likely_to_sell")}


class AnalyzeIn(BaseModel):
    property_id: int
    arv: float | None = None
    repairs: float | None = None


@router.post("/api/deals/analyze")
def deal_analyze(body: AnalyzeIn, ctx: Ctx = Depends(require_feature("deal_analyzer")), db: Session = Depends(get_db)):
    prop = db.get(Property, body.property_id)
    allowed = db.scalar(select(OrgLead.id).join(Signal, Signal.id == OrgLead.signal_id, isouter=True).where(
        OrgLead.org_id == ctx.org.id,
        (OrgLead.property_id == body.property_id) | (Signal.property_id == body.property_id)).limit(1))
    if prop is None or allowed is None:
        raise HTTPException(404, "Property not found in your leads.")
    result = analyze(db, prop, ctx.org.id, arv_override=body.arv, repairs_override=body.repairs)
    return {"property": property_dict(prop, full=True), "analysis": result.to_dict()}


@router.post("/api/leads/{lead_id}/skiptrace")
def lead_skiptrace(lead_id: int, ctx: Ctx = Depends(require_feature("contacts")), db: Session = Depends(get_db)):
    lead = db.get(OrgLead, lead_id)
    if lead is None or lead.org_id != ctx.org.id:
        raise HTTPException(404)
    sig = lead.signal
    prop = lead.property or (sig.property if sig else None)
    try:
        contact = skip_trace(db, ctx.org, prop=prop, sig=sig)
    except InsufficientCredits as exc:
        raise HTTPException(402, {"credits": True, "message": str(exc)}) from exc
    except SkipTraceError as exc:
        raise HTTPException(400, str(exc)) from exc
    award(db, ctx.user, ctx.org.id, "skip_trace")
    return {"contact": {"id": contact.id, "name": contact.name, "phones": contact.phones, "emails": contact.emails,
                        "mailing_address": contact.mailing_address}, "credits": ctx.org.credits}


@router.get("/api/farm/{territory_id}")
def farm(territory_id: int, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    terr = db.get(Territory, territory_id)
    if terr is None or terr.org_id != ctx.org.id:
        raise HTTPException(404)
    return farm_stats(db, terr, ctx.org.id)


@router.get("/reports/market/{territory_id}", response_class=HTMLResponse)
def market_report(territory_id: int, request: Request, ctx: Ctx = Depends(require_feature("market_reports")),
                  db: Session = Depends(get_db)):
    from ..web.site import templates

    terr = db.get(Territory, territory_id)
    if terr is None or terr.org_id != ctx.org.id:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "report_market.html", {
        "stats": farm_stats(db, terr, ctx.org.id), "org": ctx.org, "user": ctx.user,
        "brand": (ctx.org.settings or {}).get("brand_color") or "#7C5CFF"})


class MLSIn(BaseModel):
    mls_name: str
    base_url: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    secret: str | None = None
    vendor: str = "reso"


@router.get("/api/mls")
def mls_list(ctx: Ctx = Depends(require_feature("mls")), db: Session = Depends(get_db)):
    conns = db.scalars(select(MLSConnection).where(MLSConnection.org_id == ctx.org.id)).all()
    counts = dict(db.execute(select(Listing.connection_id, func.count()).where(Listing.org_id == ctx.org.id)
                             .group_by(Listing.connection_id)).all())
    return {"items": [{"id": c.id, "mls_name": c.mls_name, "vendor": c.vendor, "status": c.status,
                       "last_sync_at": iso(c.last_sync_at), "last_error": c.last_error,
                       "listings": counts.get(c.id, 0)} for c in conns]}


@router.post("/api/mls")
def mls_connect(body: MLSIn, ctx: Ctx = Depends(require_feature("mls")), db: Session = Depends(get_db)):
    from ..jobs import enqueue

    if body.vendor == "reso" and not (body.base_url and body.base_url.startswith("https://") and body.secret):
        raise HTTPException(400, "Enter the RESO Web API URL (https) and the credentials your MLS vendor issued.")
    conn = MLSConnection(org_id=ctx.org.id, user_id=ctx.user.id, mls_name=body.mls_name.strip()[:200],
                         vendor=body.vendor if body.vendor in ("reso", "csv") else "reso", base_url=body.base_url,
                         token_url=body.token_url, client_id=body.client_id,
                         secret_enc=encrypt_secret(body.secret) if body.secret else None,
                         status="pending" if body.vendor == "reso" else "active")
    db.add(conn)
    db.flush()
    if conn.vendor == "reso":
        enqueue(db, "sync_mls", {"connection_id": conn.id}, unique_key=f"mls:{conn.id}")
    return {"id": conn.id, "status": conn.status}


@router.post("/api/mls/{connection_id}/import")
async def mls_import(connection_id: int, file: UploadFile = File(...), ctx: Ctx = Depends(require_feature("mls")),
                     db: Session = Depends(get_db)):
    from ..realestate.mls import import_csv

    conn = db.get(MLSConnection, connection_id)
    if conn is None or conn.org_id != ctx.org.id:
        raise HTTPException(404)
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "CSV is larger than 25 MB.")
    return import_csv(db, conn, content)


# ---------------------------------------------------------------- billing

@router.get("/api/billing")
def billing_overview(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    ledger = db.scalars(select(CreditLedger).where(CreditLedger.org_id == ctx.org.id)
                        .order_by(CreditLedger.id.desc()).limit(25)).all()
    referrals = db.scalars(select(Referral).where(Referral.referrer_org_id == ctx.org.id)).all()
    contacts = db.scalar(select(func.count()).select_from(Contact).where(Contact.org_id == ctx.org.id)) or 0
    return {
        "plan": ctx.org.plan, "plan_status": ctx.org.plan_status, "trial_ends_at": iso(ctx.org.trial_ends_at),
        "founding_member": ctx.org.founding_member, "credits": ctx.org.credits or 0, "contacts_bought": contacts,
        "catalog": public_catalog(), "billing_enabled": get_settings().billing_enabled,
        "addons": {"territory": EXTRA_TERRITORY_PRICE, "exclusive_zip": EXCLUSIVE_ZIP_PRICE,
                   "credit_packs": {k: {"credits": v, "price": int(k.split("_")[1])} for k, v in CREDIT_PACKS.items()}},
        "ledger": [{"delta": l.delta, "balance": l.balance_after, "reason": l.reason, "at": iso(l.created_at)}
                   for l in ledger],
        "referral": {"code": ctx.org.referral_code, "url": f"{get_settings().public_url}/r/{ctx.org.referral_code}",
                     "signups": len(referrals), "paying": sum(1 for r in referrals if r.status == "paying"),
                     "earned_cents": sum(r.commission_cents for r in referrals)},
    }


class CheckoutIn(BaseModel):
    item: str
    interval: str = "monthly"
    quantity: int = 1


@router.post("/api/billing/checkout")
def billing_checkout(body: CheckoutIn, ctx: Ctx = Depends(require_org_admin), db: Session = Depends(get_db)):
    try:
        return {"url": checkout_url(db, ctx.org, ctx.user.email, body.item,
                                    "annual" if body.interval == "annual" else "monthly", body.quantity)}
    except BillingError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/billing/portal")
def billing_portal(ctx: Ctx = Depends(require_org_admin)):
    try:
        return {"url": portal_url(ctx.org)}
    except BillingError as exc:
        raise HTTPException(400, str(exc)) from exc


@public.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    try:
        etype = handle_webhook(db, payload, request.headers.get("stripe-signature"))
    except BillingError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"received": etype}
