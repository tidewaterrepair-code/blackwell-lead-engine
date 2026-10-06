"""Background scheduler: ingests on INGEST_HOURS and sends the digest at DIGEST_HOUR."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .db import get_engine
from .notify import push_hot_leads, send_digest
from .pipeline import rescore_all, run_all

log = logging.getLogger(__name__)


def ingest_job() -> None:
    try:
        run_all()
        push_hot_leads()
    except Exception:  # noqa: BLE001 - keep the scheduler alive
        log.exception("ingest job failed")


def digest_job() -> None:
    try:
        rescore_all()
        send_digest()
    except Exception:  # noqa: BLE001
        log.exception("digest job failed")


def main() -> None:
    settings = get_settings()
    get_engine()
    scheduler = BlockingScheduler()
    scheduler.add_job(ingest_job, CronTrigger(hour=settings.ingest_hours, minute=5), id="ingest",
                      max_instances=1, coalesce=True)
    scheduler.add_job(digest_job, CronTrigger(hour=settings.digest_hour, minute=30), id="digest",
                      max_instances=1, coalesce=True)
    log.info("worker started: ingest at hours %s, digest at %s:30", settings.ingest_hours, settings.digest_hour)
    scheduler.start()
