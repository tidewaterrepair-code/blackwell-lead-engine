"""Wholesale / flip deal analyzer: comps-based ARV, repair estimate, MAO and a deal grade."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..geo import radius_bbox
from ..intel.scoring import miles_between
from ..models import Listing, Property, Signal

MAO_RATIO = 0.70
REPAIR_PER_SQFT_BY_AGE = ((20, 12), (40, 22), (60, 32), (999, 42))  # (max age, $/sqft) cosmetic -> heavy
VIOLATION_REPAIR = 5000
DAMAGE_PER_SQFT = 15
DEFAULT_SQFT = 1600


@dataclass
class Comp:
    address: str | None
    price: float
    sqft: int | None
    sold_on: str | None
    miles: float
    source: str  # public / mls


@dataclass
class DealAnalysis:
    arv: float | None
    arv_method: str
    repairs: float
    mao: float | None
    est_value: float | None
    mortgage_est: float | None
    equity_est: float | None
    spread: float | None  # ARV - MAO - repairs (wholesaler/flipper gross margin at MAO)
    grade: str
    grade_reasons: list[str] = field(default_factory=list)
    comps: list[Comp] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def find_comps(session: Session, prop: Property, org_id: int | None, *, max_miles: float = 1.0,
               months: int = 12) -> list[Comp]:
    if prop.lat is None or prop.lng is None:
        return []
    since = utcnow() - timedelta(days=30 * months)
    s, n, w, e = radius_bbox(prop.lat, prop.lng, max_miles)
    comps: list[Comp] = []
    # The org's own MLS closed sales first (private to that org).
    if org_id is not None:
        for lst in session.scalars(select(Listing).where(
                Listing.org_id == org_id, Listing.status == "Closed", Listing.close_price.is_not(None),
                Listing.close_date >= since, Listing.lat.between(s, n), Listing.lng.between(w, e))):
            d = miles_between(prop.lat, prop.lng, lst.lat, lst.lng)
            if d <= max_miles and lst.property_id != prop.id:
                comps.append(Comp(lst.address, lst.close_price, lst.sqft,
                                  lst.close_date.date().isoformat() if lst.close_date else None, round(d, 2), "mls"))
    for sig in session.scalars(select(Signal).where(
            Signal.kind == "sale", Signal.est_value.is_not(None), Signal.posted_at >= since,
            Signal.lat.between(s, n), Signal.lng.between(w, e), Signal.property_id != prop.id)):
        if sig.est_value < 10_000:
            continue  # family transfers, $1 deeds
        d = miles_between(prop.lat, prop.lng, sig.lat, sig.lng)
        if d <= max_miles:
            sqft = sig.property.sqft if sig.property else None
            comps.append(Comp(sig.address, sig.est_value, sqft,
                              sig.posted_at.date().isoformat() if sig.posted_at else None, round(d, 2), "public"))
    if prop.sqft:
        similar = [c for c in comps if c.sqft and 0.7 * prop.sqft <= c.sqft <= 1.3 * prop.sqft]
        if len(similar) >= 3:
            comps = similar
    comps.sort(key=lambda c: (c.source != "mls", c.miles))
    return comps[:12]


def estimate_repairs(prop: Property, signals: list[Signal]) -> float:
    sqft = prop.sqft or DEFAULT_SQFT
    age = utcnow().year - prop.year_built if prop.year_built else 45
    per_sqft = next(rate for max_age, rate in REPAIR_PER_SQFT_BY_AGE if age <= max_age)
    repairs = sqft * per_sqft
    violations = sum(1 for s in signals if s.kind == "violation")
    repairs += min(3, violations) * VIOLATION_REPAIR
    if any("fire_water_restoration" in (s.tags or []) for s in signals):
        repairs += sqft * DAMAGE_PER_SQFT
    return round(repairs, -2)


def analyze(session: Session, prop: Property, org_id: int | None = None, *, arv_override: float | None = None,
            repairs_override: float | None = None) -> DealAnalysis:
    signals = session.scalars(select(Signal).where(Signal.property_id == prop.id,
                                                   ~Signal.source_id.like("manual:%"))).all()
    comps = find_comps(session, prop, org_id)
    if arv_override:
        arv, method = arv_override, "your number"
    elif comps and prop.sqft and all(c.sqft for c in comps[:5]):
        ppsf = statistics.median(c.price / c.sqft for c in comps if c.sqft)
        arv, method = round(ppsf * prop.sqft, -3), f"median $/sqft of {len(comps)} comps"
    elif len(comps) >= 3:
        arv, method = round(statistics.median(c.price for c in comps), -3), f"median of {len(comps)} comps"
    elif prop.est_value:
        arv, method = round(prop.est_value * 1.1, -3), "estimated value + 10% (few comps)"
    else:
        arv, method = None, "not enough data"
    repairs = repairs_override if repairs_override is not None else estimate_repairs(prop, signals)
    mao = round(arv * MAO_RATIO - repairs, -2) if arv else None
    spread = round(arv - mao - repairs, -2) if arv and mao is not None else None

    reasons: list[str] = []
    motivation = prop.motivation_score or 0
    equity = prop.equity_est
    value = prop.est_value or prop.assessed_value
    if mao is not None and prop.mortgage_est and mao <= prop.mortgage_est:
        grade = "F"
        reasons.append("Estimated loan balance is above the max offer")
    elif motivation >= 60 and equity and value and equity / value >= 0.5:
        grade = "A"
        reasons += ["Highly motivated", "High equity"]
    elif motivation >= 40:
        grade = "B"
        reasons.append("Motivated seller signals")
    elif motivation >= 20:
        grade = "C"
        reasons.append("Some seller signals")
    else:
        grade = "D"
        reasons.append("No distress signals yet")
    if not comps:
        reasons.append("No nearby sales found: verify ARV")
    return DealAnalysis(arv=arv, arv_method=method, repairs=repairs, mao=mao, est_value=prop.est_value,
                        mortgage_est=prop.mortgage_est, equity_est=equity, spread=spread, grade=grade,
                        grade_reasons=reasons, comps=comps)
