"""Background job handlers and the recurring schedule."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from .db import session_scope, utcnow
from .jobs import enqueue, job
from .models import MLSConnection, Org, Source

log = logging.getLogger(__name__)


@job("scrape_source")
def scrape_source(payload: dict) -> dict:
    from .ingest import run_source

    res = run_source(payload["source_id"])
    return {"fetched": res.fetched, "new": res.new_signals, "leads": res.org_leads, "error": res.error}


@job("ingest_all")
def ingest_all(_payload: dict) -> dict:
    """Fan out one scrape job per active source, then geocode."""
    with session_scope() as s:
        ids = list(s.scalars(select(Source.id).where(Source.status == "active")))
        for sid in ids:
            enqueue(s, "scrape_source", {"source_id": sid}, unique_key=f"scrape:{sid}")
        enqueue(s, "geocode", {}, run_at=utcnow() + timedelta(minutes=10), unique_key="geocode")
    return {"queued": len(ids)}


@job("geocode")
def geocode(_payload: dict) -> dict:
    from .geocode import geocode_missing
    from .ingest import fan_out_signals

    with session_scope() as s:
        ids = geocode_missing(s)
        created = fan_out_signals(s, ids) if ids else 0
    return {"geocoded": len(ids), "leads": created}


@job("backfill_org")
def backfill_org(payload: dict) -> dict:
    from .ingest import refan_org

    with session_scope() as s:
        return {"leads": refan_org(s, int(payload["org_id"]), days=int(payload.get("days", 30)))}


@job("scout_jurisdiction")
def scout_jurisdiction(payload: dict) -> dict:
    from .scout.runner import scout

    return scout(payload["fips"], requested_by=payload.get("org_id"))


@job("sync_mls")
def sync_mls(payload: dict) -> dict:
    from .realestate.mls import sync_connection

    return sync_connection(int(payload["connection_id"]))


@job("daily")
def daily(_payload: dict) -> dict:
    """Morning housekeeping: rescore, expire trials, digests, pushes, learning."""
    from .billing import expire_trials, grant_monthly_credits
    from .ingest import rescore_open_leads
    from .intel.learn import nightly
    from .jobs import prune
    from .lifecycle import run_lifecycle
    from .notify import push_hot_leads, send_digest

    out = {}
    with session_scope() as s:
        out["learn"] = bool(nightly(s))
    with session_scope() as s:
        out["rescored"] = rescore_open_leads(s)
        out["trials_expired"] = expire_trials(s)
        out["credits_granted"] = grant_monthly_credits(s)
        out["pruned"] = prune(s)
    with session_scope() as s:
        out["digests"] = sum(send_digest(s, org) for org in s.scalars(select(Org)))
        out["pushes"] = push_hot_leads(s)
        out["lifecycle_emails"] = run_lifecycle(s)
        for conn in s.scalars(select(MLSConnection).where(MLSConnection.status == "active")):
            enqueue(s, "sync_mls", {"connection_id": conn.id}, unique_key=f"mls:{conn.id}")
    return out


@job("hot_alerts")
def hot_alerts(_payload: dict) -> dict:
    from .notify import push_hot_leads

    with session_scope() as s:
        return {"pushed": push_hot_leads(s)}


@job("health_check")
def health_check(_payload: dict) -> dict:
    """Re-scout jurisdictions whose sources broke."""
    with session_scope() as s:
        broken = s.scalars(select(Source).where(Source.status == "broken", Source.jurisdiction_id.is_not(None)))
        fips = sorted({src.jurisdiction_id for src in broken})
        for f in fips:
            enqueue(s, "scout_jurisdiction", {"fips": f}, unique_key=f"scout:{f}")
    return {"rescouted": fips}


def schedule(scheduler, settings) -> None:
    """Register recurring enqueues on an APScheduler instance."""
    from apscheduler.triggers.cron import CronTrigger

    def enq(name: str, unique: str):
        def _run():
            with session_scope() as s:
                enqueue(s, name, {}, unique_key=unique)
        return _run

    scheduler.add_job(enq("ingest_all", "ingest_all"), CronTrigger(hour=settings.ingest_hours, minute=5),
                      id="ingest_all", coalesce=True, max_instances=1)
    scheduler.add_job(enq("daily", "daily"), CronTrigger(hour=settings.digest_hour, minute=0), id="daily",
                      coalesce=True, max_instances=1)
    scheduler.add_job(enq("hot_alerts", "hot_alerts"), CronTrigger(minute="*/30"), id="hot_alerts",
                      coalesce=True, max_instances=1)
    scheduler.add_job(enq("health_check", "health_check"), CronTrigger(hour=3, minute=40), id="health_check",
                      coalesce=True, max_instances=1)
