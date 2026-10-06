"""Ingestion pipeline: fetch -> store raw -> normalize -> classify -> score -> dedupe."""

from __future__ import annotations

import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .classify import classify, is_contractor_listed, worth_llm_review
from .config import get_settings, load_sources
from .db import Lead, RawRecord, Source, session_scope, utcnow
from .geocode import geocode_missing
from .scoring import dedupe_key, score_lead
from .sources import LeadInput, build_adapter

log = logging.getLogger(__name__)

DEDUPE_WINDOW = timedelta(days=90)
# Fields the user may edit in the dashboard; re-ingesting never overwrites them.
USER_FIELDS = {"status", "job_type", "customer_type", "phone", "email", "contact_name", "owner_name"}


@dataclass
class RunResult:
    source_id: str
    fetched: int = 0
    new_leads: int = 0
    updated_leads: int = 0
    skipped: int = 0
    error: str | None = None
    new_lead_ids: list[int] = field(default_factory=list)


def compute_score(lead: Lead) -> int:
    settings = get_settings()
    return score_lead(
        job_type=lead.job_type,
        kind=lead.kind,
        customer_type=lead.customer_type,
        est_value=lead.est_value,
        posted_at=lead.posted_at or lead.created_at,
        due_at=lead.due_at,
        lat=lead.lat,
        lng=lead.lng,
        base_lat=settings.base_lat,
        base_lng=settings.base_lng,
        contractor_listed=is_contractor_listed(lead.contractor_name),
        commercial=lead.commercial,
    )


def apply_lead(session: Session, source_id: str, item: LeadInput) -> tuple[Lead | None, bool]:
    """Insert or update the lead for one normalized record. Returns (lead, created)."""
    settings = get_settings()
    result = classify(
        kind=item.kind,
        title=item.title,
        description=item.description,
        permit_type=item.permit_type,
        contractor_name=item.contractor_name,
        hints=item.hints,
    )
    if item.kind == "manual":
        result.relevant = True
    elif not result.relevant and settings.ollama_url:
        text = " ".join(filter(None, [item.title, item.description, item.permit_type]))
        if worth_llm_review(text):
            from .llm import llm_classify

            result = llm_classify(text, result) or result

    existing = session.scalar(
        select(Lead).where(Lead.source_id == source_id, Lead.external_id == item.external_id)
    )
    if not result.relevant and existing is None:
        return None, False

    lead = existing or Lead(source_id=source_id, external_id=item.external_id, status="new")
    for name in ("kind", "title", "description", "permit_type", "address", "city", "zip", "est_value",
                 "owner_name", "contractor_name", "contact_name", "phone", "email", "url",
                 "posted_at", "due_at"):
        value = getattr(item, name)
        if existing is not None and name in USER_FIELDS and getattr(lead, name):
            continue
        if value is not None or existing is None:
            setattr(lead, name, value)
    if lead.url and not lead.url.lower().startswith(("http://", "https://")):
        lead.url = None  # never render javascript:/data: links from outside feeds
    if item.lat is not None and item.lng is not None:
        lead.lat, lead.lng = item.lat, item.lng
    if existing is None or lead.classified_by != "manual":
        lead.job_type = result.job_type if result.relevant else lead.job_type or "other"
        lead.customer_type = result.customer_type
        lead.classified_by = result.classified_by
        lead.confidence = result.confidence
    lead.commercial = result.commercial
    lead.score = compute_score(lead)
    lead.dedupe_key = dedupe_key(lead.address, lead.job_type)

    if existing is None:
        session.add(lead)
        session.flush()
        if lead.dedupe_key:
            original = session.scalar(
                select(Lead)
                .where(
                    Lead.dedupe_key == lead.dedupe_key,
                    Lead.id != lead.id,
                    Lead.duplicate_of_id.is_(None),
                    Lead.created_at >= utcnow() - DEDUPE_WINDOW,
                )
                .order_by(Lead.created_at)
            )
            if original is not None:
                lead.duplicate_of_id = original.id
    return lead, existing is None


def _since_for(source: Source, override: datetime | None) -> datetime:
    if override is not None:
        return override
    if source.last_success_at is not None:
        return source.last_success_at - timedelta(days=2)  # overlap catches late updates
    return utcnow() - timedelta(days=get_settings().lookback_days)


def run_source(
    source_id: str,
    config: dict,
    *,
    since: datetime | None = None,
    client: httpx.Client | None = None,
    dry_run: bool = False,
) -> RunResult:
    result = RunResult(source_id)
    with session_scope() as session:
        source = session.get(Source, source_id) or Source(id=source_id, name=config.get("name", source_id),
                                                          kind=config.get("kind", "permit"))
        source.name = config.get("name", source_id)
        source.kind = config.get("kind", source.kind)
        session.add(source)
        source.last_run_at = utcnow()
        source.last_status = "running"
        start_from = _since_for(source, since)

    adapter = build_adapter(source_id, config, client=client)

    def known(external_id: str) -> bool:
        with session_scope() as s:
            return s.scalar(
                select(RawRecord.id).where(RawRecord.source_id == source_id, RawRecord.external_id == external_id)
            ) is not None

    adapter.known = known  # type: ignore[method-assign]

    try:
        batch: list = []
        for raw in adapter.fetch(start_from):
            result.fetched += 1
            batch.append(raw)
            if len(batch) >= 200:
                _store_batch(source_id, adapter, batch, result, dry_run)
                batch = []
        if batch:
            _store_batch(source_id, adapter, batch, result, dry_run)
    except Exception as exc:  # noqa: BLE001 - one broken source must not stop the others
        log.exception("source %s failed", source_id)
        result.error = f"{type(exc).__name__}: {exc}"
        detail = traceback.format_exc(limit=3)
    else:
        detail = None

    with session_scope() as session:
        source = session.get(Source, source_id)
        source.last_fetched = result.fetched
        source.last_new_leads = result.new_leads
        if result.error:
            source.last_status = "error"
            source.last_error = f"{result.error}\n{detail}"[:4000]
        else:
            source.last_status = "ok"
            source.last_error = None
            if not dry_run:
                source.last_success_at = source.last_run_at
    return result


def _store_batch(source_id: str, adapter, batch: list, result: RunResult, dry_run: bool) -> None:
    with session_scope() as session:
        for raw in batch:
            record = session.scalar(
                select(RawRecord).where(RawRecord.source_id == source_id, RawRecord.external_id == raw.external_id)
            )
            if record is None:
                session.add(RawRecord(source_id=source_id, external_id=raw.external_id, payload=raw.payload))
            else:
                record.payload = raw.payload
                record.fetched_at = utcnow()
            item = adapter.normalize(raw.payload)
            if item is None:
                result.skipped += 1
                continue
            lead, created = apply_lead(session, source_id, item)
            if lead is None:
                result.skipped += 1
            elif created:
                result.new_leads += 1
                result.new_lead_ids.append(lead.id)
            else:
                result.updated_leads += 1
        if dry_run:
            session.rollback()


def run_all(only: list[str] | None = None, *, since: datetime | None = None) -> list[RunResult]:
    results = []
    for source_id, config in load_sources().items():
        if only and source_id not in only:
            continue
        if not only and not config.get("enabled", True):
            continue
        log.info("running source %s", source_id)
        res = run_source(source_id, config, since=since)
        log.info("%s: fetched=%s new=%s updated=%s skipped=%s error=%s", source_id, res.fetched,
                 res.new_leads, res.updated_leads, res.skipped, res.error)
        results.append(res)
    with session_scope() as session:
        n = geocode_missing(session)
        if n:
            log.info("geocoded %s leads", n)
            for lead in session.scalars(select(Lead).where(Lead.lat.is_not(None), Lead.status == "new")):
                lead.score = compute_score(lead)
    return results


def rescore_all() -> int:
    """Recency decays daily, so scores are refreshed once a day."""
    with session_scope() as session:
        leads = session.scalars(select(Lead).where(Lead.status.in_(["new", "contacted", "quoted"]))).all()
        for lead in leads:
            lead.score = compute_score(lead)
        return len(leads)


def add_manual_lead(session: Session, form: dict) -> Lead:
    item = LeadInput(
        external_id=uuid.uuid4().hex,
        kind=form.get("kind") or "manual",
        title=form.get("title") or "Manual lead",
        description=form.get("description"),
        address=form.get("address"),
        city=form.get("city"),
        contact_name=form.get("contact_name"),
        phone=form.get("phone"),
        email=form.get("email"),
        est_value=float(form["est_value"]) if form.get("est_value") else None,
        url=form.get("url"),
        posted_at=utcnow(),
    )
    lead, _ = apply_lead(session, "manual", item)
    if lead is None:  # rules found nothing; keep it anyway, it's hand-entered
        item.kind = "manual"
        lead, _ = apply_lead(session, "manual", item)
    if form.get("job_type"):
        lead.job_type = form["job_type"]
        lead.classified_by = "manual"
    if form.get("customer_type"):
        lead.customer_type = form["customer_type"]
    lead.score = compute_score(lead)
    lead.dedupe_key = dedupe_key(lead.address, lead.job_type)
    return lead
