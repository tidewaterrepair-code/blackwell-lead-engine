"""Public marketing site: landing, pricing, trade pages, programmatic SEO pages, legal, waitlist, referrals."""

from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..api.deps import get_db, rate_limit
from ..config import get_settings
from ..db import utcnow
from ..intel.scoring import normalize_address
from ..intel.taxonomy import tag_label, trades as trade_defs
from ..models import EmailSuppression, OptOut, Signal, WaitlistSignup
from ..plans import FOUNDING_SEATS, public_catalog

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")
router = APIRouter()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def money(value) -> str:
    if value is None:
        return ""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"${value / 1000:.0f}k"
    return f"${value:,.0f}"


templates.env.filters.update(money=money, slugify=slugify)
templates.env.globals.update(tag_label=tag_label, public_url=lambda: get_settings().public_url,
                             umami=lambda: (os.environ.get("UMAMI_SRC"), os.environ.get("UMAMI_WEBSITE_ID")))


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("trades", trade_defs())
    return templates.TemplateResponse(request, name, ctx)


def render_error(request: Request, status: int) -> str:
    title = {404: "Page not found", 403: "Not allowed", 429: "Slow down"}.get(status, "Something went wrong")
    return templates.get_template("error.html").render(request=request, status=status, title=title,
                                                       trades=trade_defs())


def _utm(request: Request) -> dict:
    return {k: v for k, v in request.query_params.items() if k.startswith("utm_") or k in ("ref", "gclid", "fbclid")}


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    week = utcnow() - timedelta(days=7)
    signals_week = db.scalar(select(func.count()).select_from(Signal).where(Signal.created_at >= week)) or 0
    from ..models import Org

    founding_left = max(0, FOUNDING_SEATS - (db.scalar(select(func.count()).select_from(Org).where(
        Org.founding_member.is_(True))) or 0))
    return page(request, "landing.html", plans=public_catalog(), signals_week=signals_week,
                founding_left=founding_left, utm=_utm(request))


@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return page(request, "pricing.html", plans=public_catalog())


@router.get("/for/{trade_key}", response_class=HTMLResponse)
def trade_page(trade_key: str, request: Request):
    trade = trade_defs().get(trade_key.replace("-", "_"))
    if trade is None:
        return HTMLResponse(render_error(request, 404), status_code=404)
    return page(request, "trade.html", trade=trade, plans=public_catalog())


def _public_signals():
    return select(Signal).where(Signal.duplicate_of_id.is_(None), ~Signal.source_id.like("manual:%"),
                                ~Signal.source_id.like("mls:%"), Signal.kind.in_(("permit", "bid", "subdivision", "storm")))


@router.get("/leads", response_class=HTMLResponse)
def seo_index(request: Request, db: Session = Depends(get_db)):
    """Every covered city with live public activity in the last 30 days."""
    sub = _public_signals().where(Signal.created_at >= utcnow() - timedelta(days=30), Signal.city.is_not(None),
                                  Signal.state.is_not(None)).subquery()
    rows = db.execute(select(sub.c.state, sub.c.city, func.count()).group_by(sub.c.state, sub.c.city)
                      .order_by(func.count().desc()).limit(500)).all()
    cities = [{"state": st, "city": c, "count": n, "url": f"/leads/{st.lower()}/{slugify(c)}"} for st, c, n in rows]
    return page(request, "seo_index.html", cities=cities)


@router.get("/leads/{state}/{city_slug}", response_class=HTMLResponse)
@router.get("/leads/{state}/{city_slug}/{tag}", response_class=HTMLResponse)
def seo_city(state: str, city_slug: str, request: Request, tag: str | None = None, db: Session = Depends(get_db)):
    """Programmatic SEO: live, data-rich pages like /leads/va/virginia-beach/deck."""
    state = state.upper()[:2]
    since = utcnow() - timedelta(days=30)
    stmt = _public_signals().where(Signal.state == state, Signal.created_at >= since)
    rows = [s for s in db.scalars(stmt.order_by(Signal.created_at.desc()).limit(3000))
            if slugify(s.city or "") == city_slug]
    if tag:
        rows = [s for s in rows if tag in (s.tags or [])]
    if not rows:
        return HTMLResponse(render_error(request, 404), status_code=404)
    city = rows[0].city
    counts: dict[str, int] = {}
    for s in rows:
        for t in s.tags or []:
            counts[t] = counts.get(t, 0) + 1
    total_value = sum(s.est_value or 0 for s in rows)
    # Public teaser: street name only, never the house number or owner.
    teaser = [{"job": tag_label(s.primary_tag), "street": " ".join((s.address or "").split(",")[0].split()[1:]).title(),
               "value": s.est_value, "posted": (s.posted_at or s.created_at).date().isoformat()} for s in rows[:12]]
    return page(request, "seo_city.html", state=state, city=city, tag=tag, count=len(rows), counts=sorted(
        counts.items(), key=lambda kv: -kv[1])[:12], total_value=total_value, teaser=teaser, city_slug=city_slug)


@router.get("/legal/{doc}", response_class=HTMLResponse)
def legal(doc: str, request: Request):
    if doc not in ("terms", "privacy", "acceptable-use", "data-sources"):
        return HTMLResponse(render_error(request, 404), status_code=404)
    return page(request, f"legal_{doc.replace('-', '_')}.html")


class WaitlistIn(BaseModel):
    email: str
    name: str | None = None
    audience: str | None = None
    trade: str | None = None
    city: str | None = None
    utm: dict = {}


@router.post("/api/waitlist", dependencies=[Depends(rate_limit("waitlist", 10, 3600))])
def join_waitlist(body: WaitlistIn, db: Session = Depends(get_db)):
    from ..accounts import AccountError, normalize_email

    try:
        email = normalize_email(body.email)
    except AccountError as exc:
        return Response(content=f'{{"message": "{exc}"}}', status_code=400, media_type="application/json")
    if not db.scalar(select(WaitlistSignup).where(WaitlistSignup.email == email)):
        db.add(WaitlistSignup(email=email, name=(body.name or "")[:200] or None, audience=body.audience,
                              trade=body.trade, city=(body.city or "")[:100] or None,
                              utm={k: str(v)[:100] for k, v in (body.utm or {}).items()}))
    return {"ok": True}


@router.get("/r/{code}")
def referral(code: str):
    response = RedirectResponse(f"/app/signup?ref={code}", status_code=303)
    response.set_cookie("pegasus_ref", code[:32], max_age=60 * 60 * 24 * 60, samesite="lax")
    return response


@router.get("/optout", response_class=HTMLResponse)
def optout_form(request: Request):
    return page(request, "optout.html", done=False)


@router.post("/optout", response_class=HTMLResponse, dependencies=[Depends(rate_limit("optout", 10, 3600))])
async def optout_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    address, phone, email = (str(form.get(k, "")).strip() for k in ("address", "phone", "email"))
    if address or phone or email:
        db.add(OptOut(norm_address=normalize_address(address) if address else None,
                      phone=re.sub(r"\D", "", phone)[-10:] or None, email=email.lower() or None))
    return page(request, "optout.html", done=True)


@router.get("/email/unsubscribe", response_class=HTMLResponse)
@router.post("/email/unsubscribe", response_class=HTMLResponse)
def email_unsubscribe(request: Request, t: str = "", db: Session = Depends(get_db)):
    """One-click unsubscribe (GET from the footer link, POST from List-Unsubscribe-Post)."""
    from ..lifecycle import read_unsubscribe_token

    email = read_unsubscribe_token(t)
    if email and not db.get(EmailSuppression, email):
        db.add(EmailSuppression(email=email))
    return page(request, "unsubscribed.html", ok=bool(email))


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nDisallow: /app\nDisallow: /api\nSitemap: {get_settings().public_url}/sitemap.xml\n"


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    base = get_settings().public_url
    urls = [f"{base}/", f"{base}/pricing", f"{base}/leads"] + [f"{base}/for/{k.replace('_', '-')}" for k in trade_defs()]
    cities = db.execute(select(Signal.state, Signal.city).where(Signal.state.is_not(None), Signal.city.is_not(None),
                                                                Signal.created_at >= utcnow() - timedelta(days=30))
                        .distinct().limit(5000)).all()
    urls += [f"{base}/leads/{st.lower()}/{slugify(c)}" for st, c in cities]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{body}</urlset>", media_type="application/xml")
