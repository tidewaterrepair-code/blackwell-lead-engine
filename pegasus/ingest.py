"""Ingestion: fetch -> raw -> normalize -> classify -> signal -> property -> predictions -> fan-out.

Signals are shared: a jurisdiction is scraped once no matter how many customers
watch it. Fan-out then creates each matching org's private OrgLead rows.
"""

from __future__ import annotations

import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import new_session, session_scope, utcnow
from .geo import Located, TerritoryIndex
from .intel.classify import classify, is_contractor_listed, worth_llm_review
from .intel.predict import forecast
from .intel.scoring import ScoreInput, dedupe_key, normalize_address, score
from .intel.taxonomy import matching_trades, trades as trade_defs
from .models import Org, OrgLead, Prediction, Property, RawRecord, Signal, Source, Territory
from .plans import effective_plan
from .sources import LeadInput, build_adapter

log = logging.getLogger(__name__)

DEDUPE_WINDOW = timedelta(days=90)
SIGNAL_FIELDS = ("kind", "title", "description", "permit_type", "address", "city", "state", "zip", "county_fips",
                 "est_value", "owner_name", "contractor_name", "contact_name", "phone", "email", "url",
                 "posted_at", "due_at", "radius_miles")


@dataclass
class RunResult:
    source_id: str
    fetched: int = 0
    new_signals: int = 0
    updated_signals: int = 0
    skipped: int = 0
    org_leads: int = 0
    error: str | None = None
    new_signal_ids: list[int] = field(default_factory=list)


# ---------------------------------------------------------------- signals

def classify_item(item: LeadInput):
    result = classify(kind=item.kind, title=item.title, description=item.description,
                      permit_type=item.permit_type, contractor_name=item.contractor_name, hints=item.hints)
    if not result.relevant and item.kind in ("permit", "bid", "request"):
        from .intel.llm import llm_classify

        text = " ".join(filter(None, [item.title, item.description, item.permit_type]))
        if worth_llm_review(text):
            result = llm_classify(text, result) or result
    return result


def upsert_signal(session: Session, source_id: str, item: LeadInput) -> tuple[Signal | None, bool]:
    """Insert or update the shared signal for one normalized record. Returns (signal, created)."""
    result = classify_item(item)
    existing = session.scalar(select(Signal).where(Signal.source_id == source_id,
                                                   Signal.external_id == item.external_id))
    if not result.relevant and existing is None and item.kind not in ("manual",):
        return None, False

    sig = existing or Signal(source_id=source_id, external_id=item.external_id)
    for name in SIGNAL_FIELDS:
        value = getattr(item, name)
        if value is not None or existing is None:
            setattr(sig, name, value)
    if sig.url and not sig.url.lower().startswith(("http://", "https://")):
        sig.url = None  # never render javascript:/data: links from outside feeds
    if item.lat is not None and item.lng is not None:
        sig.lat, sig.lng = item.lat, item.lng
    enrich_location(sig)
    if sig.classified_by != "manual":
        sig.tags = result.tags
        sig.primary_tag = result.job_type
        sig.classified_by = result.classified_by
        sig.confidence = result.confidence
    sig.commercial = result.commercial
    sig.data = {**(sig.data or {}), **({"facts": item.facts} if item.facts else {}),
                "customer_type": result.customer_type}
    sig.dedupe_key = dedupe_key(sig.address, sig.primary_tag)

    if existing is None:
        session.add(sig)
        session.flush()
        if sig.dedupe_key:
            original = session.scalar(
                select(Signal).where(Signal.dedupe_key == sig.dedupe_key, Signal.id != sig.id,
                                     Signal.duplicate_of_id.is_(None),
                                     Signal.created_at >= utcnow() - DEDUPE_WINDOW)
                .order_by(Signal.created_at))
            if original is not None:
                sig.duplicate_of_id = original.id
    link_property(session, sig, item)
    return sig, existing is None


_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\s*$")


def enrich_location(sig) -> None:
    """Fill zip / state / county from whatever location facts the signal has."""
    from .geodata import city_county, locate_point, zip_info

    if not sig.zip and sig.address:
        m = _ZIP_RE.search(sig.address)
        if m:
            sig.zip = m.group(1)
    if sig.zip:
        info = zip_info(sig.zip)
        if info:
            sig.state = sig.state or info["state"]
            sig.county_fips = sig.county_fips or info["county_fips"]
    if not sig.county_fips and sig.lat is not None and sig.lng is not None:
        sig.county_fips = locate_point(sig.lat, sig.lng)
    if not sig.county_fips and sig.city and sig.state:
        sig.county_fips = city_county(sig.city, sig.state)


def link_property(session: Session, sig: Signal, item: LeadInput | None = None) -> Property | None:
    """Attach the signal to its property record (created on first sight) and merge known facts."""
    norm = normalize_address(sig.address)
    if not norm or not norm[0].isdigit():
        return None
    facts = (item.facts if item else None) or (sig.data or {}).get("facts") or {}
    prop = None
    if facts.get("parcel_id"):
        prop = session.scalar(select(Property).where(Property.parcel_id == str(facts["parcel_id"])))
    if prop is None:
        stmt = select(Property).where(Property.norm_address == norm)
        if sig.zip:
            stmt = stmt.where((Property.zip == sig.zip[:5]) | Property.zip.is_(None))
        elif sig.city:
            stmt = stmt.where((func.lower(Property.city) == sig.city.lower()) | Property.city.is_(None))
        prop = session.scalars(stmt).first()
    if prop is None:
        prop = Property(norm_address=norm, address=sig.address, distress=[], data={})
        session.add(prop)
    prop.city = prop.city or sig.city
    prop.state = prop.state or sig.state
    prop.zip = prop.zip or (sig.zip[:5] if sig.zip else None)
    prop.county_fips = prop.county_fips or sig.county_fips
    if sig.lat is not None and prop.lat is None:
        prop.lat, prop.lng = sig.lat, sig.lng
    if sig.owner_name and (sig.kind in ("sale", "tax_delinquent", "violation", "foreclosure", "probate")
                           or not prop.owner_name):
        prop.owner_name = sig.owner_name
    from .realestate.properties import merge_facts

    merge_facts(prop, sig, facts)
    session.flush()
    sig.property_id = prop.id
    return prop


def make_predictions(session: Session, sig: Signal, weights: dict | None = None) -> list[Prediction]:
    if sig.duplicate_of_id or not sig.tags:
        return []
    anchor = sig.posted_at or sig.created_at or utcnow()
    out = []
    for fc in forecast(sig.tags, sig.kind, anchor, weights=weights):
        if fc.window_end < utcnow():
            continue  # already over
        pred = session.scalar(select(Prediction).where(Prediction.signal_id == sig.id,
                                                       Prediction.trade == fc.trade, Prediction.tag == fc.tag))
        if pred is None:
            pred = Prediction(signal_id=sig.id, trade=fc.trade, tag=fc.tag)
            session.add(pred)
        pred.window_start, pred.window_end = fc.window_start, fc.window_end
        pred.probability, pred.reason, pred.rule = fc.probability, fc.reason, fc.rule
        out.append(pred)
    session.flush()
    return out


# ---------------------------------------------------------------- fan-out

class FanOut:
    """Matches signals/predictions to every org whose territory and trades cover them."""

    def __init__(self, session: Session):
        self.session = session
        territories = session.scalars(select(Territory)).all()
        self.index = TerritoryIndex(territories)
        self.orgs = {o.id: o for o in session.scalars(select(Org)).all()}
        # Exclusive ZIP territories: (trade, zip) -> owning org
        self.exclusive: dict[tuple[str, str], int] = {}
        for t in territories:
            if t.exclusive and t.kind == "zip":
                org = self.orgs.get(t.org_id)
                for trade in (t.trades or (org.trades if org else [])):
                    for z in t.data.get("zips", []):
                        self.exclusive[(trade, z)] = t.org_id
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        self.month_counts = dict(session.execute(
            select(OrgLead.org_id, func.count()).where(OrgLead.created_at >= month_start)
            .group_by(OrgLead.org_id)).all())
        self.created = 0

    def _allowed(self, org: Org, trade: str, zip_code: str | None) -> bool:
        owner = self.exclusive.get((trade, (zip_code or "")[:5]))
        return owner is None or owner == org.id

    def _base(self, org: Org, territory: Territory) -> tuple[float | None, float | None]:
        if org.base_lat is not None:
            return org.base_lat, org.base_lng
        if territory.kind == "radius":
            return territory.data.get("lat"), territory.data.get("lng")
        return None, None

    def _upsert(self, org: Org, territory: Territory, ref: str, lead_type: str, trade: str, sc, **ids) -> None:
        plan = effective_plan(org)
        lead = self.session.scalar(select(OrgLead).where(OrgLead.org_id == org.id, OrgLead.ref == ref))
        if lead is None:
            if plan.monthly_lead_cap is not None and self.month_counts.get(org.id, 0) >= plan.monthly_lead_cap:
                return
            lead = OrgLead(org_id=org.id, ref=ref, lead_type=lead_type, status="new", **ids)
            lead.visible_at = utcnow() + timedelta(days=plan.lead_delay_days)
            self.session.add(lead)
            self.month_counts[org.id] = self.month_counts.get(org.id, 0) + 1
            self.created += 1
        lead.territory_id, lead.trade = territory.id, trade
        if lead.status in ("new", "saved", "contacted", "quoted"):
            lead.score, lead.reasons = sc.value, sc.reasons

    def signal(self, sig: Signal, predictions: list[Prediction] | None = None) -> None:
        if sig.duplicate_of_id or sig.source_id.startswith(("manual:", "mls:")):
            return  # private records are never shared with other orgs
        loc = Located(sig.lat, sig.lng, sig.zip, sig.county_fips, sig.city, sig.state, sig.radius_miles)
        prop = sig.property
        all_trades = trade_defs()
        for territory in self.index.candidates(loc):
            org = self.orgs.get(territory.org_id)
            if org is None:
                continue
            org_trades = territory.trades or org.trades or []
            base_lat, base_lng = self._base(org, territory)
            for trade in matching_trades(sig.tags, sig.kind, org_trades):
                if not self._allowed(org, trade, sig.zip):
                    continue
                tdef = all_trades[trade]
                sc = score(ScoreInput(
                    kind=sig.kind, est_value=sig.est_value, posted_at=sig.posted_at or sig.created_at,
                    lat=sig.lat, lng=sig.lng, due_at=sig.due_at,
                    contractor_listed=is_contractor_listed(sig.contractor_name), commercial=sig.commercial,
                    customer_type=(sig.data or {}).get("customer_type", "homeowner"), trade_group=tdef.group,
                    commercial_ok=trade in ("general_contractor", "supplier", "electrician", "hvac", "plumber"),
                    motivation=prop.motivation_score if (prop and tdef.group == "realestate") else None,
                    default_ticket=tdef.ticket,
                ), base_lat=base_lat, base_lng=base_lng)
                self._upsert(org, territory, f"s:{sig.id}", "signal", trade, sc, signal_id=sig.id)
                break  # one lead per signal per org, under its best-matching trade
            for pred in predictions or []:
                if pred.trade not in org_trades or not self._allowed(org, pred.trade, sig.zip):
                    continue
                tdef = all_trades[pred.trade]
                sc = score(ScoreInput(
                    kind=sig.kind, est_value=None, posted_at=sig.posted_at, lat=sig.lat, lng=sig.lng,
                    trade_group=tdef.group, window_start=pred.window_start, window_end=pred.window_end,
                    probability=pred.probability, default_ticket=tdef.ticket,
                ), base_lat=base_lat, base_lng=base_lng)
                self._upsert(org, territory, f"p:{pred.id}", "prediction", pred.trade, sc,
                             signal_id=sig.id, prediction_id=pred.id)


def fan_out_signals(session: Session, signal_ids: list[int], weights: dict | None = None) -> int:
    if not signal_ids:
        return 0
    fan = FanOut(session)
    if not fan.index.spatial and not fan.index.by_zip and not fan.index.by_fips and not fan.index.by_city:
        return 0
    for chunk_start in range(0, len(signal_ids), 500):
        chunk = signal_ids[chunk_start:chunk_start + 500]
        sigs = session.scalars(select(Signal).where(Signal.id.in_(chunk))).all()
        preds_by_signal: dict[int, list[Prediction]] = {}
        for p in session.scalars(select(Prediction).where(Prediction.signal_id.in_(chunk))):
            preds_by_signal.setdefault(p.signal_id, []).append(p)
        for sig in sigs:
            fan.signal(sig, preds_by_signal.get(sig.id))
    session.flush()
    return fan.created


# ---------------------------------------------------------------- running sources

def _since_for(source: Source, override: datetime | None) -> datetime:
    if override is not None:
        return override
    if source.last_success_at is not None:
        return source.last_success_at - timedelta(days=2)  # overlap catches late updates
    days = int((source.config or {}).get("lookback_days", get_settings().lookback_days))
    return utcnow() - timedelta(days=days)


def run_source(source_id: str, *, since: datetime | None = None, client: httpx.Client | None = None,
               dry_run: bool = False) -> RunResult:
    result = RunResult(source_id)
    with session_scope() as session:
        source = session.get(Source, source_id)
        if source is None:
            raise KeyError(f"unknown source {source_id!r}")
        config = {**(source.config or {}), "type": source.type, "kind": source.kind, "name": source.name}
        source.last_run_at = utcnow()
        source.last_status = "running"
        start_from = _since_for(source, since)

    adapter = build_adapter(source_id, config, client=client)

    def known(external_id: str) -> bool:
        with session_scope() as s:
            return s.scalar(select(RawRecord.id).where(RawRecord.source_id == source_id,
                                                       RawRecord.external_id == external_id)) is not None

    adapter.known = known  # type: ignore[method-assign]
    detail = None
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

    with session_scope() as session:
        source = session.get(Source, source_id)
        source.last_fetched = result.fetched
        source.last_new = result.new_signals
        if result.error:
            source.last_status = "error"
            source.last_error = f"{result.error}\n{detail}"[:4000]
            source.consecutive_failures += 1
            if source.consecutive_failures >= 5 and source.status == "active":
                source.status = "broken"
        else:
            source.last_status, source.last_error, source.consecutive_failures = "ok", None, 0
            if not dry_run:
                source.last_success_at = source.last_run_at
                if source.status == "broken":  # the outage cleared: put it back on the schedule
                    source.status = "active"
    return result


def _store_batch(source_id: str, adapter, batch: list, result: RunResult, dry_run: bool) -> None:
    from .intel.learn import load_weights

    session = new_session()
    try:
        weights = load_weights(session)
        touched: list[int] = []
        for raw in batch:
            record = session.scalar(select(RawRecord).where(RawRecord.source_id == source_id,
                                                            RawRecord.external_id == raw.external_id))
            if record is None:
                session.add(RawRecord(source_id=source_id, external_id=raw.external_id, payload=raw.payload))
            else:
                record.payload, record.fetched_at = raw.payload, utcnow()
            item = adapter.apply_defaults(adapter.normalize(raw.payload))
            if item is None:
                result.skipped += 1
                continue
            sig, created = upsert_signal(session, source_id, item)
            if sig is None:
                result.skipped += 1
                continue
            make_predictions(session, sig, weights)
            touched.append(sig.id)
            if created:
                result.new_signals += 1
                result.new_signal_ids.append(sig.id)
            else:
                result.updated_signals += 1
        from .realestate.properties import refresh_scores

        refresh_scores(session, [s for s in touched])
        result.org_leads += fan_out_signals(session, touched, weights)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def active_source_ids(session: Session) -> list[str]:
    return list(session.scalars(select(Source.id).where(Source.status == "active").order_by(Source.id)))


def run_all(only: list[str] | None = None, *, since: datetime | None = None) -> list[RunResult]:
    from .geocode import geocode_missing

    with session_scope() as session:
        ids = only or active_source_ids(session)
    results = []
    for source_id in ids:
        res = run_source(source_id, since=since)
        log.info("%s: fetched=%s new=%s updated=%s skipped=%s leads=%s error=%s", source_id, res.fetched,
                 res.new_signals, res.updated_signals, res.skipped, res.org_leads, res.error)
        results.append(res)
    with session_scope() as session:
        geocoded = geocode_missing(session)
        if geocoded:
            fan_out_signals(session, geocoded)
    return results


def refan_org(session: Session, org_id: int, days: int = 30) -> int:
    """Backfill a new org (or a new territory) with recent signals."""
    ids = list(session.scalars(select(Signal.id).where(
        Signal.created_at >= utcnow() - timedelta(days=days), Signal.duplicate_of_id.is_(None))))
    fan = FanOut(session)
    fan.orgs = {k: v for k, v in fan.orgs.items() if k == org_id}
    for chunk_start in range(0, len(ids), 500):
        chunk = ids[chunk_start:chunk_start + 500]
        preds: dict[int, list[Prediction]] = {}
        for p in session.scalars(select(Prediction).where(Prediction.signal_id.in_(chunk))):
            preds.setdefault(p.signal_id, []).append(p)
        for sig in session.scalars(select(Signal).where(Signal.id.in_(chunk))):
            fan.signal(sig, preds.get(sig.id))
    session.flush()
    return fan.created


def rescore_open_leads(session: Session) -> int:
    """Recency decays and prediction windows move, so open leads are rescored daily."""
    n = 0
    leads = session.scalars(select(OrgLead).where(OrgLead.status.in_(("new", "saved", "contacted", "quoted")))).all()
    by_org = {o.id: o for o in session.scalars(select(Org))}
    all_trades = trade_defs()
    for lead in leads:
        sig, org = lead.signal, by_org.get(lead.org_id)
        if sig is None or org is None:
            continue
        tdef = all_trades.get(lead.trade or "")
        pred = lead.prediction
        sc = score(ScoreInput(
            kind=sig.kind, est_value=None if pred else sig.est_value, posted_at=sig.posted_at or sig.created_at,
            lat=sig.lat, lng=sig.lng, due_at=sig.due_at,
            contractor_listed=is_contractor_listed(sig.contractor_name), commercial=sig.commercial,
            customer_type=(sig.data or {}).get("customer_type", "homeowner"),
            trade_group=tdef.group if tdef else "trades",
            window_start=pred.window_start if pred else None, window_end=pred.window_end if pred else None,
            probability=pred.probability if pred else None,
            motivation=sig.property.motivation_score if (sig.property and tdef and tdef.group == "realestate") else None,
            default_ticket=tdef.ticket if tdef else None,
        ), base_lat=org.base_lat, base_lng=org.base_lng)
        lead.score, lead.reasons = sc.value, sc.reasons
        n += 1
    return n


# ---------------------------------------------------------------- seed sources

def sync_seed_sources(session: Session) -> int:
    """Upsert sources.yaml entries into the sources table (origin=yaml)."""
    from .config import load_sources

    n = 0
    for sid, cfg in load_sources().items():
        src = session.get(Source, sid)
        conf = {k: v for k, v in cfg.items() if k not in ("type", "kind", "name", "enabled", "jurisdiction")}
        if src is None:
            src = Source(id=sid, origin="yaml")
            session.add(src)
        if src.origin != "yaml":
            continue
        src.name, src.type, src.kind = cfg.get("name", sid), cfg["type"], cfg.get("kind", "permit")
        src.config = conf
        if cfg.get("jurisdiction"):
            from .geodata import ensure_jurisdiction

            j = ensure_jurisdiction(session, str(cfg["jurisdiction"]))
            kinds = set(j.coverage_kinds or [])
            if cfg.get("enabled", True):
                kinds.add(cfg.get("kind", "permit"))
                j.coverage = "covered" if len(kinds) >= 2 else "partial"
            j.coverage_kinds = sorted(kinds)
        src.jurisdiction_id = cfg.get("jurisdiction")
        if src.status in (None, "active", "disabled"):
            src.status = "active" if cfg.get("enabled", True) else "disabled"
        n += 1
    session.flush()
    return n


def sync_seed_sources_safely(attempts: int = 3) -> int:
    """sync_seed_sources in its own transaction, tolerating a concurrent first boot.

    Several web workers (and the worker service) start at once; on an empty database they race
    to insert the same rows. The loser gets an IntegrityError and simply retries, by which time
    the rows exist and the upsert path runs.
    """
    from sqlalchemy.exc import IntegrityError

    for attempt in range(attempts):
        try:
            with session_scope() as s:
                return sync_seed_sources(s)
        except IntegrityError:
            if attempt == attempts - 1:
                raise
    return 0

