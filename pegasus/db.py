"""Engine/session handling. Postgres in production, SQLite for dev and tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_sessionmaker: sessionmaker | None = None


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def get_engine(url: str | None = None) -> Engine:
    global _engine, _sessionmaker
    if _engine is None or url is not None:
        from . import models  # noqa: F401 - register tables

        url = url or get_settings().database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})
            event.listen(_engine, "connect", _sqlite_pragmas)
        else:
            _engine = create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)
        _sessionmaker = sessionmaker(bind=_engine, expire_on_commit=False)
        if url.startswith("sqlite") or get_settings().env != "production":
            # Production Postgres is managed by Alembic (`pegasus db upgrade`).
            Base.metadata.create_all(_engine)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _sessionmaker is not None
    session = _sessionmaker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def new_session() -> Session:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker()
