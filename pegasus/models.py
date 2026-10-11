"""Pegasus data model.

Key idea: *signals* (public events: permits, bids, sales, violations...) and
*properties* are shared by every customer; each customer (org) gets private
*org_leads* rows holding their score, status, notes and pipeline state.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

SIGNAL_KINDS = {
    "permit": "Permit",
    "bid": "Bid / RFP",
    "request": "Homeowner request",
    "subdivision": "Subdivision / plat",
    "sale": "Property sale",
    "violation": "Code violation",
    "tax_delinquent": "Tax delinquent",
    "foreclosure": "Pre-foreclosure",
    "probate": "Probate / estate",
    "eviction": "Eviction filing",
    "storm": "Storm event",
    "listing": "MLS listing",
    "manual": "Manual",
}
LEAD_STATUSES = {"new": "New", "saved": "Saved", "contacted": "Contacted", "quoted": "Quoted",
                 "won": "Won", "lost": "Lost", "passed": "Passed"}
OPEN_STATUSES = ("new", "saved", "contacted", "quoted")
ROLES = ("owner", "admin", "member")


# ---------------------------------------------------------------- accounts

class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(16), default="trades")  # trades / realestate / both
    trades: Mapped[list] = mapped_column(JSON, default=list)  # trade keys, see trades/packs.yaml
    plan: Mapped[str] = mapped_column(String(32), default="free")
    plan_status: Mapped[str] = mapped_column(String(32), default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    founding_member: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    credits: Mapped[int] = mapped_column(Integer, default=0)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True)
    referred_by_org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"))
    base_lat: Mapped[float | None] = mapped_column(Float)
    base_lng: Mapped[float | None] = mapped_column(Float)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # digest prefs, ntfy topic, goals...
    utm: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    territories: Mapped[list["Territory"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(300))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_on: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    badges: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    org: Mapped[Org] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16), default="member")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Territory(Base):
    """An area an org watches. kind: radius | zip | county | city | polygon."""

    __tablename__ = "territories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)  # {lat,lng,miles} | {zips:[]} | {fips:[]} | {city,state} | {geojson}
    trades: Mapped[list] = mapped_column(JSON, default=list)  # empty = all org trades
    exclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    # Bounding box prefilter (null for zip/county/city kinds).
    min_lat: Mapped[float | None] = mapped_column(Float)
    max_lat: Mapped[float | None] = mapped_column(Float)
    min_lng: Mapped[float | None] = mapped_column(Float)
    max_lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    org: Mapped[Org] = relationship(back_populates="territories")


# ---------------------------------------------------------------- coverage

class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "51810" (FIPS) or "51-norfolk"
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(2), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="county")  # county / city / place
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[str] = mapped_column(String(16), default="none")  # none / scouting / partial / covered
    coverage_kinds: Mapped[list] = mapped_column(JSON, default=list)
    last_scouted_at: Mapped[datetime | None] = mapped_column(DateTime)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(16), default="yaml")  # yaml / scout / admin
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / pending_review / disabled / broken
    confidence: Mapped[float | None] = mapped_column(Float)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_fetched: Mapped[int] = mapped_column(Integer, default=0)
    last_new: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- shared intelligence

class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    norm_address: Mapped[str] = mapped_column(String(300), index=True)
    parcel_id: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10), index=True)
    county_fips: Mapped[str | None] = mapped_column(String(8))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    owner_mailing_address: Mapped[str | None] = mapped_column(String(300))
    owner_state: Mapped[str | None] = mapped_column(String(2))
    absentee: Mapped[bool | None] = mapped_column(Boolean)
    vacant: Mapped[bool | None] = mapped_column(Boolean)
    property_type: Mapped[str | None] = mapped_column(String(50))
    year_built: Mapped[int | None] = mapped_column(Integer)
    sqft: Mapped[int | None] = mapped_column(Integer)
    beds: Mapped[float | None] = mapped_column(Float)
    baths: Mapped[float | None] = mapped_column(Float)
    lot_sqft: Mapped[int | None] = mapped_column(Integer)
    assessed_value: Mapped[float | None] = mapped_column(Float)
    est_value: Mapped[float | None] = mapped_column(Float)
    last_sale_date: Mapped[datetime | None] = mapped_column(DateTime)
    last_sale_price: Mapped[float | None] = mapped_column(Float)
    mortgage_est: Mapped[float | None] = mapped_column(Float)
    rental: Mapped[bool | None] = mapped_column(Boolean)
    distress: Mapped[list] = mapped_column(JSON, default=list)  # active distress signal kinds
    motivation_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    sell_probability: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @property
    def equity_est(self) -> float | None:
        value = self.est_value or self.assessed_value
        if value is None:
            return None
        return value - (self.mortgage_est or 0)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_signals_geo", "lat", "lng"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    permit_type: Mapped[str | None] = mapped_column(String(300))
    tags: Mapped[list] = mapped_column(JSON, default=list)  # job tags, see trades/tags.yaml
    primary_tag: Mapped[str] = mapped_column(String(40), default="other", index=True)
    classified_by: Mapped[str] = mapped_column(String(16), default="rules")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    commercial: Mapped[bool] = mapped_column(Boolean, default=False)
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10), index=True)
    county_fips: Mapped[str | None] = mapped_column(String(8), index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geocode_tried: Mapped[bool] = mapped_column(Boolean, default=False)
    radius_miles: Mapped[float | None] = mapped_column(Float)  # area signals (storms)
    est_value: Mapped[float | None] = mapped_column(Float)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    contractor_name: Mapped[str | None] = mapped_column(String(200), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(300), index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"))
    brief: Mapped[str | None] = mapped_column(Text)  # AI "why this lead" summary
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    property: Mapped[Property | None] = relationship()


class Prediction(Base):
    """A forecast job: 'this new home will need a deck in 3-12 months'."""

    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("signal_id", "trade", "tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), index=True)
    trade: Mapped[str] = mapped_column(String(40), index=True)
    tag: Mapped[str] = mapped_column(String(40))
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    probability: Mapped[float] = mapped_column(Float, default=0.5)
    reason: Mapped[str] = mapped_column(String(500))
    rule: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    signal: Mapped[Signal] = relationship()


# ---------------------------------------------------------------- per-org pipeline

class OrgLead(Base):
    __tablename__ = "org_leads"
    __table_args__ = (
        UniqueConstraint("org_id", "ref"),
        Index("ix_org_leads_feed", "org_id", "status", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    ref: Mapped[str] = mapped_column(String(40))  # "s:<signal>" | "p:<prediction>" | "h:<property>"
    lead_type: Mapped[str] = mapped_column(String(16))  # signal / prediction / property
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    territory_id: Mapped[int | None] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"))
    trade: Mapped[str | None] = mapped_column(String(40))  # which of the org's trades matched
    score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)  # short "why" chips
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime)
    value_won: Mapped[float | None] = mapped_column(Float)
    visible_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)  # free plan delay
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    signal: Mapped[Signal | None] = relationship()
    prediction: Mapped[Prediction | None] = relationship()
    property: Mapped[Property | None] = relationship()
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Activity.created_at.desc()"
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_lead_id: Mapped[int] = mapped_column(ForeignKey("org_leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32))  # note / call / quote / status / email / text
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[OrgLead] = relationship(back_populates="activities")


class Contact(Base):
    """Skip-trace result bought by an org (private to that org)."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id", ondelete="SET NULL"), index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(String(200))
    phones: Mapped[list] = mapped_column(JSON, default=list)  # [{number,type,dnc,litigator}]
    emails: Mapped[list] = mapped_column(JSON, default=list)
    mailing_address: Mapped[str | None] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(32), default="batchdata")
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))  # monthly_grant / purchase / skip_trace / referral / refund
    ref: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    referred_org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="signed_up")  # signed_up / paying / churned
    commission_rate: Mapped[float] = mapped_column(Float, default=0.30)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BillingEvent(Base):
    """Processed Stripe webhook ids (idempotency) and revenue facts for Mission Control."""

    __tablename__ = "billing_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    type: Mapped[str] = mapped_column(String(100))
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- MLS (private per org)

class MLSConnection(Base):
    __tablename__ = "mls_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mls_name: Mapped[str] = mapped_column(String(200))
    vendor: Mapped[str] = mapped_column(String(32), default="reso")  # reso / csv
    base_url: Mapped[str | None] = mapped_column(String(500))
    token_url: Mapped[str | None] = mapped_column(String(500))
    client_id: Mapped[str | None] = mapped_column(String(300))
    secret_enc: Mapped[str | None] = mapped_column(Text)  # encrypted client secret / token
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / active / error
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("connection_id", "listing_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("mls_connections.id", ondelete="CASCADE"))
    listing_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), index=True)  # Active / Pending / Closed / Expired / Withdrawn / Canceled
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    zip: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    list_price: Mapped[float | None] = mapped_column(Float)
    close_price: Mapped[float | None] = mapped_column(Float)
    sqft: Mapped[int | None] = mapped_column(Integer)
    beds: Mapped[float | None] = mapped_column(Float)
    baths: Mapped[float | None] = mapped_column(Float)
    year_built: Mapped[int | None] = mapped_column(Integer)
    list_date: Mapped[datetime | None] = mapped_column(DateTime)
    close_date: Mapped[datetime | None] = mapped_column(DateTime)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    days_on_market: Mapped[int | None] = mapped_column(Integer)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- platform

class Job(Base):
    """Database-backed job queue (no Redis needed)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_ready", "status", "run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    unique_key: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued / running / done / failed
    run_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ScoutJob(Base):
    __tablename__ = "scout_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    requested_by_org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued / running / review / done / failed
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Event(Base):
    """Product analytics + gamification log."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WaitlistSignup(Base):
    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    audience: Mapped[str | None] = mapped_column(String(32))  # trades / realestate
    trade: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(100))
    utm: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    address: Mapped[str] = mapped_column(String(400), primary_key=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    county_fips: Mapped[str | None] = mapped_column(String(8))
    zip: Mapped[str | None] = mapped_column(String(10))
    looked_up_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OptOut(Base):
    """Privacy removal requests (CCPA-style). Matching properties/contacts are suppressed."""

    __tablename__ = "opt_outs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    norm_address: Mapped[str | None] = mapped_column(String(300), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ModelParam(Base):
    """Learned parameters (prediction weights, likely-to-sell weights, calibration reports)."""

    __tablename__ = "model_params"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
