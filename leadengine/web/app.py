"""Dashboard: FastAPI + server-rendered Jinja templates (no build step, no CDN)."""

from __future__ import annotations

import csv
import hmac
import io
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from ..config import get_settings, load_sources
from ..db import (
    CUSTOMER_TYPES,
    JOB_TYPES,
    LEAD_KINDS,
    STATUSES,
    Activity,
    Lead,
    RawRecord,
    Source,
    get_engine,
    session_scope,
    utcnow,
)
from ..classify import is_contractor_listed
from ..pipeline import add_manual_lead, compute_score

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
OPEN_STATUSES = ("new", "contacted", "quoted")
PAGE_SIZE = 50
# Map pin letters: a second channel next to color so job types never rely on hue alone.
JOB_LETTERS = {"new_construction": "N", "house_framing": "F", "garage_framing": "G", "addition": "A",
               "deck": "D", "kitchen": "K", "bath": "B", "remodel": "R", "other": "?"}

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_engine()
    if not settings.app_password:
        log.warning("APP_PASSWORD is not set: the dashboard is open to anyone who can reach it")
    yield


app = FastAPI(title="Blackwell Lead Engine", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 24 * 30,
                   same_site="lax", https_only=settings.public_url.startswith("https"))
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


# ---------------------------------------------------------------- template helpers

def money(value) -> str:
    if value is None:
        return ""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"${value / 1000:.0f}k"
    return f"${value:,.0f}"


def ago(value: datetime | None) -> str:
    if value is None:
        return ""
    delta = utcnow() - value
    if delta.days < 0:
        days = -delta.days
        return "tomorrow" if days == 1 else f"in {days} days"
    if delta.days == 0:
        hours = delta.seconds // 3600
        return "just now" if hours == 0 else f"{hours}h ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < 60:
        return f"{delta.days} days ago"
    return value.strftime("%b %d, %Y")


def score_band(score: int) -> str:
    return "hot" if score >= settings.hot_lead_score else "warm" if score >= settings.digest_min_score else "cool"


templates.env.filters.update(money=money, ago=ago)
templates.env.globals.update(
    JOB_TYPES=JOB_TYPES, CUSTOMER_TYPES=CUSTOMER_TYPES, LEAD_KINDS=LEAD_KINDS, STATUSES=STATUSES,
    JOB_LETTERS=JOB_LETTERS, score_band=score_band, has_contractor=is_contractor_listed,
)


# ---------------------------------------------------------------- auth / csrf

class LoginRequired(Exception):
    pass


@app.exception_handler(LoginRequired)
async def _login_redirect(request: Request, _exc: LoginRequired):
    return RedirectResponse(f"/login?{urlencode({'next': request.url.path})}", status_code=303)


def require_login(request: Request) -> None:
    if settings.app_password and not request.session.get("auth"):
        raise LoginRequired()


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, token: str) -> None:
    if not hmac.compare_digest(token or "", request.session.get("csrf") or ""):
        raise HTTPException(status_code=400, detail="Form expired, go back and try again.")


def get_db():
    with session_scope() as session:
        yield session


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("nav", name.split(".")[0])
    return templates.TemplateResponse(
        request, name,
        {"csrf": csrf_token(request), "auth_enabled": bool(settings.app_password), **ctx},
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    return render(request, "login.html", next=next, error=None)


@app.post("/login")
def login(request: Request, password: str = Form(...), next: str = Form("/"), csrf: str = Form("")):
    check_csrf(request, csrf)
    if settings.app_password and hmac.compare_digest(password, settings.app_password):
        request.session["auth"] = True
        return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/",
                                status_code=303)
    return render(request, "login.html", next=next, error="Wrong password")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------- lead queries

FILTER_KEYS = ("q", "job_type", "kind", "customer_type", "city", "status", "min_score", "days", "sort", "dupes")


def lead_filters(request: Request) -> dict:
    params = {k: request.query_params.get(k, "") for k in FILTER_KEYS}
    params["status"] = params["status"] or "open"
    params["sort"] = params["sort"] or "score"
    return params


def filtered_query(f: dict):
    stmt = select(Lead)
    if f.get("dupes") != "1":
        stmt = stmt.where(Lead.duplicate_of_id.is_(None))
    if f.get("q"):
        like = f"%{f['q']}%"
        stmt = stmt.where(or_(Lead.title.ilike(like), Lead.description.ilike(like), Lead.address.ilike(like),
                              Lead.contractor_name.ilike(like), Lead.owner_name.ilike(like)))
    for key in ("job_type", "kind", "customer_type", "city"):
        if f.get(key):
            stmt = stmt.where(getattr(Lead, key) == f[key])
    status = f.get("status")
    if status == "open":
        stmt = stmt.where(Lead.status.in_(OPEN_STATUSES))
    elif status and status != "all":
        stmt = stmt.where(Lead.status == status)
    if f.get("min_score", "").isdigit():
        stmt = stmt.where(Lead.score >= int(f["min_score"]))
    if f.get("days", "").isdigit():
        since = utcnow() - timedelta(days=int(f["days"]))
        stmt = stmt.where(func.coalesce(Lead.posted_at, Lead.created_at) >= since)
    order = {
        "newest": [func.coalesce(Lead.posted_at, Lead.created_at).desc()],
        "value": [Lead.est_value.desc().nulls_last(), Lead.score.desc()],
        "score": [Lead.score.desc(), func.coalesce(Lead.posted_at, Lead.created_at).desc()],
    }.get(f.get("sort"), [Lead.score.desc()])
    return stmt.order_by(*order)


def query_string(f: dict, **overrides) -> str:
    merged = {**f, **overrides}
    return urlencode({k: v for k, v in merged.items() if v not in ("", None)})


# ---------------------------------------------------------------- pages

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def feed(request: Request, db: Session = Depends(get_db), page: int = 1):
    f = lead_filters(request)
    stmt = filtered_query(f)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    leads = db.scalars(stmt.offset((max(page, 1) - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    day_ago = utcnow() - timedelta(days=1)
    stats = {
        "new_today": db.scalar(select(func.count()).where(Lead.created_at >= day_ago, Lead.duplicate_of_id.is_(None))),
        "hot": db.scalar(select(func.count()).where(Lead.score >= settings.hot_lead_score, Lead.status == "new",
                                                    Lead.duplicate_of_id.is_(None))),
        "open_bids": db.scalar(select(func.count()).where(Lead.kind == "bid", Lead.status.in_(OPEN_STATUSES),
                                                          or_(Lead.due_at.is_(None), Lead.due_at >= utcnow()))),
        "pipeline": db.scalar(select(func.count()).where(Lead.status.in_(("contacted", "quoted")))),
    }
    cities = [c for c in db.scalars(select(Lead.city).distinct().order_by(Lead.city)) if c]
    return render(request, "feed.html", leads=leads, f=f, total=total, page=page, page_size=PAGE_SIZE,
                  stats=stats, cities=cities, qs=lambda **kw: query_string(f, **kw))


@app.get("/leads/{lead_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def lead_detail(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404)
    raw = db.scalar(select(RawRecord).where(RawRecord.source_id == lead.source_id,
                                            RawRecord.external_id == lead.external_id))
    dupes = db.scalars(select(Lead).where(Lead.duplicate_of_id == lead.id)).all()
    original = db.get(Lead, lead.duplicate_of_id) if lead.duplicate_of_id else None
    return render(request, "lead.html", lead=lead, raw=raw, dupes=dupes, original=original, nav="feed")


@app.post("/leads/{lead_id}/status", dependencies=[Depends(require_login)])
def set_status(request: Request, lead_id: int, status: str = Form(...), csrf: str = Form(""),
               back: str = Form(""), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    lead = db.get(Lead, lead_id)
    if lead is None or status not in STATUSES:
        raise HTTPException(404)
    if lead.status != status:
        db.add(Activity(lead_id=lead.id, kind="status", body=f"{lead.status_label} → {STATUSES[status]}"))
        lead.status = status
    return RedirectResponse(back if back.startswith("/") else f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/note", dependencies=[Depends(require_login)])
def add_note(request: Request, lead_id: int, body: str = Form(...), kind: str = Form("note"),
             csrf: str = Form(""), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404)
    if body.strip():
        db.add(Activity(lead_id=lead.id, kind=kind if kind in ("note", "call", "quote") else "note",
                        body=body.strip()))
        lead.updated_at = utcnow()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/edit", dependencies=[Depends(require_login)])
def edit_lead(request: Request, lead_id: int, csrf: str = Form(""), job_type: str = Form(""),
              customer_type: str = Form(""), contact_name: str = Form(""), phone: str = Form(""),
              email: str = Form(""), est_value: str = Form(""), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404)
    if job_type in JOB_TYPES and job_type != lead.job_type:
        lead.job_type, lead.classified_by = job_type, "manual"
    if customer_type in CUSTOMER_TYPES:
        lead.customer_type = customer_type
    lead.contact_name = contact_name.strip() or lead.contact_name
    lead.phone = phone.strip() or lead.phone
    lead.email = email.strip() or lead.email
    try:
        lead.est_value = float(est_value.replace("$", "").replace(",", "")) if est_value.strip() else lead.est_value
    except ValueError:
        pass
    lead.score = compute_score(lead)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.get("/map", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def map_page(request: Request, db: Session = Depends(get_db)):
    f = lead_filters(request)
    cities = [c for c in db.scalars(select(Lead.city).distinct().order_by(Lead.city)) if c]
    return render(request, "map.html", f=f, cities=cities, qs=lambda **kw: query_string(f, **kw),
                  base=(settings.base_lat, settings.base_lng))


@app.get("/api/leads.geojson", dependencies=[Depends(require_login)])
def leads_geojson(request: Request, db: Session = Depends(get_db)):
    stmt = filtered_query(lead_filters(request)).where(Lead.lat.is_not(None)).limit(2000)
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [l.lng, l.lat]},
            "properties": {"id": l.id, "title": l.title, "job_type": l.job_type, "job": l.job_label,
                           "letter": JOB_LETTERS.get(l.job_type, "?"), "score": l.score,
                           "customer": l.customer_label, "value": money(l.est_value), "when": ago(l.posted_at)},
        }
        for l in db.scalars(stmt)
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features})


@app.get("/pipeline", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def pipeline_page(request: Request, db: Session = Depends(get_db)):
    columns = {}
    for status in ("contacted", "quoted", "won", "lost"):
        columns[status] = db.scalars(
            select(Lead).where(Lead.status == status).order_by(Lead.updated_at.desc()).limit(100)
        ).all()
    won_value = db.scalar(select(func.sum(Lead.est_value)).where(Lead.status == "won")) or 0
    return render(request, "pipeline.html", columns=columns, won_value=won_value)


@app.get("/builders", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def builders_page(request: Request, db: Session = Depends(get_db), days: int = 90):
    since = utcnow() - timedelta(days=days)
    is_new = case((Lead.job_type.in_(("new_construction", "house_framing")), 1), else_=0)
    rows = db.execute(
        select(
            Lead.contractor_name,
            func.count().label("permits"),
            func.sum(is_new).label("new_homes"),
            func.sum(Lead.est_value).label("value"),
            func.max(func.coalesce(Lead.posted_at, Lead.created_at)).label("latest"),
            func.max(Lead.city).label("city"),
        )
        .where(Lead.kind == "permit", Lead.contractor_name.is_not(None),
               func.coalesce(Lead.posted_at, Lead.created_at) >= since, Lead.duplicate_of_id.is_(None))
        .group_by(Lead.contractor_name)
        .order_by(func.sum(is_new).desc(), func.count().desc())
        .limit(100)
    ).all()
    rows = [r for r in rows if is_contractor_listed(r.contractor_name)]
    return render(request, "builders.html", rows=rows, days=days)


@app.get("/builders/{name}", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def builder_detail(request: Request, name: str, db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).where(Lead.contractor_name == name)
                       .order_by(func.coalesce(Lead.posted_at, Lead.created_at).desc()).limit(200)).all()
    return render(request, "builder.html", name=name, leads=leads, nav="builders")


@app.get("/bids", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def bids_page(request: Request, db: Session = Depends(get_db), past: int = 0):
    stmt = select(Lead).where(Lead.kind == "bid", Lead.duplicate_of_id.is_(None))
    if not past:
        stmt = stmt.where(Lead.status.in_(OPEN_STATUSES), or_(Lead.due_at.is_(None), Lead.due_at >= utcnow()))
    bids = db.scalars(stmt.order_by(Lead.due_at.is_(None), Lead.due_at, Lead.created_at.desc()).limit(300)).all()
    return render(request, "bids.html", bids=bids, past=past, now=utcnow())


@app.get("/add", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def add_form(request: Request):
    return render(request, "add.html")


@app.post("/add", dependencies=[Depends(require_login)])
async def add_submit(request: Request, db: Session = Depends(get_db)):
    form = {k: (v.strip() if isinstance(v, str) else v) for k, v in (await request.form()).items()}
    check_csrf(request, form.get("csrf", ""))
    if not form.get("title"):
        return render(request, "add.html", error="Give the lead a short title.", form=form)
    try:
        lead = add_manual_lead(db, form)
    except ValueError:
        return render(request, "add.html", error="Value must be a number.", form=form)
    db.flush()
    if form.get("note"):
        db.add(Activity(lead_id=lead.id, kind="note", body=form["note"]))
    return RedirectResponse(f"/leads/{lead.id}", status_code=303)


_running: set[str] = set()


def _run_in_background(source_ids: list[str]) -> None:
    from ..notify import push_hot_leads
    from ..pipeline import run_all

    try:
        run_all(source_ids)
        push_hot_leads()
    except Exception:  # noqa: BLE001
        log.exception("manual run failed")
    finally:
        _running.difference_update(source_ids)


@app.get("/sources", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def sources_page(request: Request, db: Session = Depends(get_db)):
    configs = load_sources()
    rows = []
    for sid, cfg in configs.items():
        src = db.get(Source, sid)
        lead_count = db.scalar(select(func.count()).where(Lead.source_id == sid))
        rows.append({"id": sid, "cfg": cfg, "src": src, "leads": lead_count, "running": sid in _running})
    return render(request, "sources.html", rows=rows)


@app.post("/sources/run", dependencies=[Depends(require_login)])
def run_sources(request: Request, csrf: str = Form(""), source: str = Form("")):
    check_csrf(request, csrf)
    configs = load_sources()
    ids = [source] if source in configs else [k for k, v in configs.items() if v.get("enabled")]
    ids = [i for i in ids if i not in _running]
    if ids:
        _running.update(ids)
        threading.Thread(target=_run_in_background, args=(ids,), daemon=True).start()
    return RedirectResponse("/sources", status_code=303)


@app.get("/export.csv", dependencies=[Depends(require_login)])
def export_csv(request: Request, db: Session = Depends(get_db)):
    columns = ["id", "score", "status", "kind", "job_type", "customer_type", "title", "description", "address",
               "city", "zip", "est_value", "owner_name", "contractor_name", "contact_name", "phone", "email",
               "url", "posted_at", "due_at", "source_id", "external_id"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for lead in db.scalars(filtered_query(lead_filters(request)).limit(10000)):
        writer.writerow([getattr(lead, c) if getattr(lead, c) is not None else "" for c in columns])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=leads.csv"})


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
