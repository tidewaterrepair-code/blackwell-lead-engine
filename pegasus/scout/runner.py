"""Source Scout orchestration: discover -> probe -> map -> validate -> propose (or auto-approve)."""

from __future__ import annotations

import logging
import os
import re

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope, utcnow
from ..geodata import county, ensure_jurisdiction
from ..models import ScoutJob, Source
from .build import build_proposal
from .discover import discover

log = logging.getLogger(__name__)
AUTO_APPROVE_AT = float(os.environ.get("SCOUT_AUTO_APPROVE", "0.85"))  # set >1 to always require review


def _source_id(fips: str, kind: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or kind
    return f"scout-{fips}-{kind}-{slug}"[:80]


def scout(fips: str, requested_by: int | None = None, client: httpx.Client | None = None) -> dict:
    c = county(fips)
    if c is None:
        return {"error": f"unknown county {fips}"}
    with session_scope() as s:
        j = ensure_jurisdiction(s, fips)
        job = ScoutJob(jurisdiction_id=fips, requested_by_org_id=requested_by, status="running", log=[])
        s.add(job)
        s.flush()
        job_id = job.id
        j.coverage = "scouting"
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True,
                                    headers={"User-Agent": get_settings().user_agent})
    proposals, log_lines = [], []
    try:
        candidates = discover(fips, client)
        log_lines.append(f"found {len(candidates)} candidate sources")
        for cand in candidates[:20]:
            prop = build_proposal(cand, c, client)
            proposals.append(prop)
            log_lines.append(f"{cand.platform} {cand.kind} '{cand.title[:60]}': confidence {prop.confidence}"
                             + (f" ({prop.problem})" if prop.problem else ""))
    finally:
        if own:
            client.close()

    approved = pending = 0
    with session_scope() as s:
        job = s.get(ScoutJob, job_id)
        j = ensure_jurisdiction(s, fips)
        kinds = set(j.coverage_kinds or [])
        for prop in sorted(proposals, key=lambda p: -p.confidence):
            if prop.confidence < 0.3 or not prop.config:
                continue
            sid = _source_id(fips, prop.kind, prop.candidate.title)
            if s.get(Source, sid):
                continue
            status = "active" if prop.confidence >= AUTO_APPROVE_AT else "pending_review"
            s.add(Source(id=sid, jurisdiction_id=fips, name=prop.candidate.title[:200] or sid, type=prop.type,
                         kind=prop.kind, config={**prop.config, "scout_checks": prop.checks,
                                                 "scout_sample": prop.sample, "scout_url": prop.candidate.url},
                         origin="scout", status=status, confidence=prop.confidence))
            if status == "active":
                approved += 1
                kinds.add(prop.kind)
            else:
                pending += 1
        j.coverage_kinds = sorted(kinds)
        j.coverage = "covered" if len(kinds) >= 2 else ("partial" if kinds else ("scouting" if pending else "none"))
        j.last_scouted_at = utcnow()
        job.candidates = [{**p.candidate.to_dict(), "type": p.type, "kind": p.kind, "confidence": p.confidence,
                           "checks": p.checks, "problem": p.problem} for p in proposals]
        job.log = log_lines
        job.status = "review" if pending else "done"
        job.finished_at = utcnow()
    log.info("scout %s: %s approved, %s pending review", fips, approved, pending)
    return {"fips": fips, "candidates": len(proposals), "approved": approved, "pending_review": pending}


def approve_source(source_id: str) -> None:
    from ..jobs import enqueue

    with session_scope() as s:
        src = s.get(Source, source_id)
        if src is None:
            raise KeyError(source_id)
        src.status = "active"
        if src.jurisdiction_id:
            j = ensure_jurisdiction(s, src.jurisdiction_id)
            kinds = set(j.coverage_kinds or []) | {src.kind}
            j.coverage_kinds = sorted(kinds)
            j.coverage = "covered" if len(kinds) >= 2 else "partial"
        enqueue(s, "scrape_source", {"source_id": source_id}, unique_key=f"scrape:{source_id}")


def pending_sources() -> list[dict]:
    with session_scope() as s:
        return [{"id": src.id, "name": src.name, "type": src.type, "kind": src.kind, "jurisdiction": src.jurisdiction_id,
                 "confidence": src.confidence, "checks": (src.config or {}).get("scout_checks"),
                 "sample": (src.config or {}).get("scout_sample"), "url": (src.config or {}).get("scout_url")}
                for src in s.scalars(select(Source).where(Source.status == "pending_review")
                                     .order_by(Source.confidence.desc()))]
