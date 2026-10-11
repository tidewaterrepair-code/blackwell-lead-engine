"""Worker process: job queue consumers + the recurring schedule."""

from __future__ import annotations

import logging
import signal
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from . import tasks
from .config import get_settings
from .db import get_engine, session_scope
from .ingest import sync_seed_sources
from .jobs import work_forever

log = logging.getLogger(__name__)


def main(threads: int = 3) -> None:
    settings = get_settings()
    get_engine()
    with session_scope() as s:
        sync_seed_sources(s)
    scheduler = BackgroundScheduler()
    tasks.schedule(scheduler, settings)
    scheduler.start()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    workers = [threading.Thread(target=work_forever, args=(stop,), daemon=True, name=f"worker-{i}")
               for i in range(threads)]
    for w in workers:
        w.start()
    log.info("worker started: %s threads; ingest at %s:05, daily at %s:00", threads, settings.ingest_hours,
             settings.digest_hour)
    stop.wait()
    scheduler.shutdown(wait=False)
    log.info("worker stopping")
