"""A small database-backed job queue (works on Postgres and SQLite; no Redis).

    @job("scrape_source")
    def scrape_source(payload): ...

    enqueue(session, "scrape_source", {"source_id": "norfolk-permits"}, unique_key="scrape:norfolk-permits")
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import new_session, utcnow
from .models import Job

log = logging.getLogger(__name__)

HANDLERS: dict[str, Callable[[dict], dict | None]] = {}


def job(name: str):
    def register(fn):
        HANDLERS[name] = fn
        return fn

    return register


def enqueue(session: Session, name: str, payload: dict | None = None, *, run_at: datetime | None = None,
            unique_key: str | None = None, max_attempts: int = 3) -> Job | None:
    """Queue a job. With unique_key, skips if the same job is already queued or running."""
    if unique_key:
        existing = session.scalar(select(Job).where(Job.unique_key == unique_key,
                                                    Job.status.in_(("queued", "running"))))
        if existing is not None:
            return None
    j = Job(name=name, payload=payload or {}, run_at=run_at or utcnow(), unique_key=unique_key,
            max_attempts=max_attempts)
    session.add(j)
    session.flush()
    return j


def _claim(session: Session) -> Job | None:
    stmt = (select(Job).where(Job.status == "queued", Job.run_at <= utcnow())
            .order_by(Job.run_at, Job.id).limit(1))
    if session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    for _ in range(5):
        j = session.scalar(stmt)
        if j is None:
            return None
        # Compare-and-set so two workers can never run the same job (SQLite has no SKIP LOCKED).
        claimed = session.execute(
            update(Job).where(Job.id == j.id, Job.status == "queued")
            .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1)
        ).rowcount
        session.commit()
        if claimed:
            session.refresh(j)
            return j
    return None


def run_one() -> bool:
    """Run the next ready job. Returns False when the queue is empty."""
    session = new_session()
    try:
        j = _claim(session)
        if j is None:
            return False
        handler = HANDLERS.get(j.name)
        try:
            if handler is None:
                raise RuntimeError(f"no handler registered for job {j.name!r}")
            result = handler(dict(j.payload or {}))
        except Exception as exc:  # noqa: BLE001 - a failing job must not kill the worker
            log.exception("job %s#%s failed", j.name, j.id)
            j.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"[:4000]
            if j.attempts < j.max_attempts:
                j.status = "queued"
                j.run_at = utcnow() + timedelta(minutes=2 ** j.attempts)
            else:
                j.status, j.finished_at = "failed", utcnow()
        else:
            j.status, j.finished_at = "done", utcnow()
            j.result = result if isinstance(result, dict) else None
        session.commit()
        return True
    finally:
        session.close()


def drain(max_jobs: int = 1000) -> int:
    """Run queued jobs until empty (used by tests and the CLI)."""
    n = 0
    while n < max_jobs and run_one():
        n += 1
    return n


def work_forever(stop: threading.Event, poll_seconds: float = 2.0) -> None:
    from . import tasks  # noqa: F401 - registers handlers

    while not stop.is_set():
        try:
            if not run_one():
                stop.wait(poll_seconds)
        except Exception:  # noqa: BLE001 - e.g. database restarting
            log.exception("worker loop error")
            stop.wait(10)


def prune(session: Session, keep_days: int = 14) -> int:
    old = session.scalars(select(Job).where(Job.status.in_(("done", "failed")),
                                            Job.finished_at < utcnow() - timedelta(days=keep_days))).all()
    for j in old:
        session.delete(j)
    return len(old)
