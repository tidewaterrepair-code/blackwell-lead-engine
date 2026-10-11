"""Public marketing site: landing, pricing, trade pages, programmatic SEO pages, legal, waitlist, referrals."""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
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
def breadcrumb_ld(*crumbs: tuple[str, str]) -> Markup:
    """schema.org BreadcrumbList for search results: breadcrumb_ld(("Home", "/"), ("Roofing leads", "/for/roofer"))."""
    base = get_settings().public_url
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": f"{base}{path}"} for i, (name, path) in enumerate(crumbs)]}
    return Markup('<script type="application/ld+json">' + json.dumps(data).replace("</", "<\\/") + "</script>")


templates.env.globals.update(breadcrumb_ld=breadcrumb_ld)
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


LANDING_FAQ = [
    ("How do contractors find construction leads before anyone else?",
     "Watch the public record. Building permits, plats, bid boards and recorded sales are filed days to months before "
     "a job is advertised. Pegasus reads those sources every morning in your area, scores each one for your trade, and "
     "predicts the follow-on work (a new home means framing, roofing, HVAC, flooring and a deck, in that order)."),
    ("Where do building permit leads come from?",
     "From city and county permit portals and open-data APIs. Pegasus normalizes them into one feed with the address, "
     "job type, value and date, removes duplicates, and adds owner and property context where public records allow."),
    ("How do real estate agents and investors find off-market properties?",
     "By stacking public signals: tax delinquency, pre-foreclosure filings, probate, code violations, long ownership "
     "with high equity and absentee owners. Pegasus combines them into a motivation score and a likely-to-sell "
     "forecast built only on property facts, never on protected characteristics."),
    ("What are expired listing leads, and can I use my MLS?",
     "Listings that expired, were withdrawn or cancelled without selling. Agents can connect their own MLS feed "
     "through their MLS's licensed data vendor (or upload an export), and expired listings in their farm become "
     "private leads the moment they change."),
    ("Is it legal to use public records for leads?",
     "Yes. Permits, recorded sales and court filings are public. Pegasus flags Do Not Call and known litigator "
     "numbers, follows fair-housing rules, and is not a consumer reporting agency, so it can't be used for credit, "
     "employment or tenant screening."),
    ("How is this different from Angi, HomeAdvisor or Thumbtack?",
     "Marketplaces sell homeowner requests that are often sent to several pros at once. Pegasus finds projects at the "
     "source, before they're advertised, and you can lock an exclusive ZIP so no other Pegasus customer in your trade "
     "gets those leads."),
    ("Do you cover my city?",
     "Pick any US city, county or ZIP. Where sources already exist, leads start right away. Where they don't, Source "
     "Scout finds and maps the local data, usually within days."),
    ("What does it cost, and can I cancel?",
     "Plans start at $79 a month after a 14-day free trial with no card. The first 100 customers keep 40% off for "
     "life. Cancel any time from the billing page."),
]


def _landing_stats(db: Session) -> dict:
    now = utcnow()
    week = _public_signals().where(Signal.created_at >= now - timedelta(days=7)).subquery()
    count_week = db.scalar(select(func.count()).select_from(week)) or 0
    value_week = db.scalar(select(func.coalesce(func.sum(week.c.est_value), 0))) or 0
    count_day = db.scalar(select(func.count()).select_from(
        _public_signals().where(Signal.created_at >= now - timedelta(days=1)).subquery())) or 0
    month = _public_signals().where(Signal.created_at >= now - timedelta(days=30), Signal.city.is_not(None),
                                    Signal.state.is_not(None)).subquery()
    cities = db.execute(select(month.c.state, month.c.city, func.count()).group_by(month.c.state, month.c.city)
                        .order_by(func.count().desc()).limit(8)).all()
    recent = db.scalars(_public_signals().where(Signal.address.is_not(None)).order_by(Signal.created_at.desc())
                        .limit(8)).all()
    feed = [{"job": tag_label(r.primary_tag), "street": " ".join((r.address or "").split(",")[0].split()[1:]).title(),
             "city": r.city, "value": r.est_value, "kind": r.kind,
             "hours": max(1, int((now - (r.created_at or now)).total_seconds() // 3600))} for r in recent]
    return {"count_week": count_week, "value_week": value_week, "count_day": count_day, "feed": feed,
            "cities": [{"state": st, "city": c, "count": n, "url": f"/leads/{st.lower()}/{slugify(c)}"}
                       for st, c, n in cities]}


def _landing_jsonld(plans: list[dict], faq: list[tuple[str, str]]) -> str:
    base = get_settings().public_url
    paid = [p for p in plans if p["monthly"]]
    graph = [
        {"@type": "Organization", "@id": f"{base}/#org", "name": "Pegasus", "alternateName": "Pegasus Leads",
         "description": "Data and lead technology for construction trades and real estate professionals.",
         "url": base, "logo": f"{base}/static/brand/pegasus-512.png"},
        {"@type": "WebSite", "@id": f"{base}/#website", "url": base, "name": "Pegasus",
         "publisher": {"@id": f"{base}/#org"}},
        {"@type": "SoftwareApplication", "name": "Pegasus", "applicationCategory": "BusinessApplication",
         "operatingSystem": "Web, iOS, Android", "url": f"{base}/app/signup",
         "description": "Construction leads and real estate leads from building permits, bids, property sales, storms "
                        "and distressed-property records, scored for your trade and predicted before they're advertised.",
         "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": min(p["monthly"] for p in paid),
                    "highPrice": max(p["monthly"] for p in paid), "offerCount": len(paid)},
         "publisher": {"@id": f"{base}/#org"}},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q,
                                             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}).replace("</", "<\\/")


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    from ..models import Org

    founding_taken = db.scalar(select(func.count()).select_from(Org).where(Org.founding_member.is_(True))) or 0
    plans = public_catalog()
    return page(request, "landing.html", plans=plans, stats=_landing_stats(db), faq=LANDING_FAQ,
                founding_left=max(0, FOUNDING_SEATS - founding_taken), founding_taken=founding_taken,
                founding_total=FOUNDING_SEATS, jsonld=_landing_jsonld(plans, LANDING_FAQ), utm=_utm(request),
                digest_hour=get_settings().digest_hour)


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
    q = (request.query_params.get("q") or "").strip()[:80]
    if q:
        cities = [c for c in cities if q.lower() in f"{c['city']}, {c['state']}".lower()]
    return page(request, "seo_index.html", cities=cities, q=q)


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
    return f"User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api\nSitemap: {get_settings().public_url}/sitemap.xml\n"


@router.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt(db: Session = Depends(get_db)):
    """Plain-language summary for AI assistants and answer engines (llmstxt.org convention)."""
    base = get_settings().public_url
    trades = ", ".join(t.label for k, t in trade_defs().items() if k not in ("real_estate_agent", "investor"))
    plans = "; ".join(f"{p['label']} ${p['monthly']}/mo" for p in public_catalog() if p["monthly"])
    lines = [
        "# Pegasus", "",
        "> Pegasus is data and lead technology for construction trades and real estate professionals. It turns public "
        "records (building permits, bids, plats, property sales, storm reports, tax and court filings) and agents' own "
        "MLS feeds into a ranked, predicted daily list of jobs and likely sellers for one customer's trade and area.", "",
        f"- Trades covered: {trades}.",
        "- Real estate: off-market and distressed properties, likely-to-sell forecasts, expired listings via the "
        "agent's licensed MLS feed, deal analyzer (ARV, repairs, maximum allowable offer).",
        "- Coverage: any US city or county; new areas are mapped by Source Scout.",
        f"- Pricing: 14-day free trial, no card. {plans}. First 100 customers get 40% off for life.",
        "- Compliance: Do Not Call and litigator flags, fair-housing safe scoring, not a consumer reporting agency.", "",
        "## Pages", "",
        f"- [Home]({base}/): what Pegasus does and how it works",
        f"- [Pricing]({base}/pricing): plans, credits and add-ons",
        f"- [Leads by city]({base}/leads): live counts of new projects by city",
        f"- [Data sources]({base}/legal/data-sources): where the data comes from",
    ]
    lines += [f"- [{t.label} leads]({base}/for/{k.replace('_', '-')})" for k, t in trade_defs().items()]
    return "\n".join(lines) + "\n"


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    base = get_settings().public_url
    urls = [f"{base}/", f"{base}/pricing", f"{base}/leads"] + [f"{base}/for/{k.replace('_', '-')}" for k in trade_defs()]
    cities = db.execute(select(Signal.state, Signal.city).where(Signal.state.is_not(None), Signal.city.is_not(None),
                                                                Signal.created_at >= utcnow() - timedelta(days=30))
                        .distinct().limit(5000)).all()
    urls += [f"{base}/leads/{st.lower()}/{slugify(c)}" for st, c in cities]
    today = utcnow().date().isoformat()  # these pages are rebuilt from live data every day
    body = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{body}</urlset>", media_type="application/xml")
