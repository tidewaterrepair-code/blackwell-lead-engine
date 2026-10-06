"""Database models and session handling (SQLite by default, any SQLAlchemy URL works)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import get_settings

JOB_TYPES = {
    "new_construction": "New construction",
    "house_framing": "House framing",
    "garage_framing": "Garage",
    "addition": "Addition",
    "deck": "Deck / porch",
    "kitchen": "Kitchen remodel",
    "bath": "Bath remodel",
    "remodel": "Other remodel",
    "other": "Other",
}
CUSTOMER_TYPES = {"homeowner": "Homeowner", "builder": "Builder / GC", "public": "Public bid"}
LEAD_KINDS = {"permit": "Permit", "bid": "Bid / RFP", "request": "Homeowner request",
              "subdivision": "Subdivision", "manual": "Manual"}
STATUSES = {"new": "New", "contacted": "Contacted", "quoted": "Quoted",
            "won": "Won", "lost": "Lost", "ignored": "Ignored"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(16))  # ok / error / running
    last_error: Mapped[str | None] = mapped_column(Text)
    last_fetched: Mapped[int] = mapped_column(Integer, default=0)
    last_new_leads: Mapped[int] = mapped_column(Integer, default=0)


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    permit_type: Mapped[str | None] = mapped_column(String(200))
    job_type: Mapped[str] = mapped_column(String(32), index=True, default="other")
    customer_type: Mapped[str] = mapped_column(String(32), index=True, default="homeowner")
    classified_by: Mapped[str] = mapped_column(String(16), default="rules")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    commercial: Mapped[bool] = mapped_column(Boolean, default=False)
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    zip: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geocode_tried: Mapped[bool] = mapped_column(Boolean, default=False)
    est_value: Mapped[float | None] = mapped_column(Float)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    contractor_name: Mapped[str | None] = mapped_column(String(200), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(300), index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    activities: Mapped[list["Activity"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Activity.created_at.desc()"
    )

    @property
    def job_label(self) -> str:
        return JOB_TYPES.get(self.job_type, self.job_type)

    @property
    def customer_label(self) -> str:
        return CUSTOMER_TYPES.get(self.customer_type, self.customer_type)

    @property
    def kind_label(self) -> str:
        return LEAD_KINDS.get(self.kind, self.kind)

    @property
    def status_label(self) -> str:
        return STATUSES.get(self.status, self.status)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # note / status / call / quote
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="activities")


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    address: Mapped[str] = mapped_column(String(400), primary_key=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    looked_up_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


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
        url = url or get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _sqlite_pragmas)
        _sessionmaker = sessionmaker(bind=_engine, expire_on_commit=False)
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
