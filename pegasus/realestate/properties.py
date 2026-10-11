"""Property intelligence: fact merging, the distress stack, motivation and likely-to-sell.

All scores are explainable heuristics until enough outcomes exist for the
learning loop (intel/learn.py) to calibrate them. Fair Housing: only property
and public-record facts are used, never anything about the owner as a person
(age, race, religion, family status, disability, national origin, sex).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..intel.scoring import normalize_address
from ..models import Property, Signal
from ..sources.base import parse_date, parse_money

DISTRESS_KINDS = ("foreclosure", "tax_delinquent", "probate", "eviction", "violation")
DISTRESS_WINDOW = timedelta(days=540)
APPRECIATION = 0.04  # per year, conservative long-run US average
MORTGAGE_RATE = 0.06
LTV = 0.80

MOTIVATION_WEIGHTS = {
    "foreclosure": 35, "tax_delinquent": 25, "probate": 25, "eviction": 15, "violation": 12,
    "vacant": 15, "absentee": 10, "out_of_state": 5, "long_owned": 10, "high_equity": 10,
    "expired_listing": 10, "damage": 10, "old_house": 5, "free_and_clear": 8,
}
# Log-odds contributions for listing within 12 months (base ~6%/yr turnover).
SELL_BASE_LOGIT = math.log(0.06 / 0.94)
SELL_WEIGHTS = {
    "foreclosure": 1.1, "probate": 0.9, "tax_delinquent": 0.6, "eviction": 0.5, "violation": 0.3,
    "vacant": 0.6, "absentee": 0.35, "out_of_state": 0.2, "long_owned": 0.35, "high_equity": 0.25,
    "expired_listing": 1.0, "damage": 0.4, "prep_permits": 0.5, "recent_purchase": -1.2,
}
FACTOR_LABELS = {
    "foreclosure": "Pre-foreclosure", "tax_delinquent": "Behind on taxes", "probate": "Estate / probate",
    "eviction": "Eviction filed", "violation": "Code violations", "vacant": "Vacant", "absentee": "Absentee owner",
    "out_of_state": "Out-of-state owner", "long_owned": "Owned 15+ years", "high_equity": "High equity",
    "expired_listing": "Listing expired", "damage": "Fire/water damage", "old_house": "50+ years old",
    "free_and_clear": "Likely paid off", "prep_permits": "Recent pre-sale work", "recent_purchase": "Bought recently",
}


def _int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", ""))) if value not in (None, "") else None
    except ValueError:
        return None


def remaining_balance(price: float, sold_on: datetime, now: datetime) -> float:
    """Remaining principal on a 30-year loan at 80% LTV taken out at purchase (estimate)."""
    principal = price * LTV
    months_paid = max(0, (now.year - sold_on.year) * 12 + now.month - sold_on.month)
    if months_paid >= 360:
        return 0.0
    r = MORTGAGE_RATE / 12
    payment = principal * r / (1 - (1 + r) ** -360)
    return max(0.0, principal * (1 + r) ** months_paid - payment * ((1 + r) ** months_paid - 1) / r)


def merge_facts(prop: Property, sig: Signal, facts: dict) -> None:
    """Fold facts from one signal into the property record."""
    if facts.get("parcel_id") and not prop.parcel_id:
        prop.parcel_id = str(facts["parcel_id"])
    for attr, key in (("year_built", "year_built"), ("sqft", "sqft")):
        value = _int(facts.get(key))
        if value and (attr != "year_built" or 1700 < value <= utcnow().year + 1):
            setattr(prop, attr, value)
    assessed = parse_money(facts.get("assessed_value"))
    if assessed:
        prop.assessed_value = assessed
    if facts.get("mailing_address"):
        prop.owner_mailing_address = str(facts["mailing_address"])[:300]
    if facts.get("owner_state"):
        prop.owner_state = str(facts["owner_state"]).upper()[:2]
    if sig.kind == "sale":
        sold_on = parse_date(facts.get("sale_date")) or sig.posted_at
        price = parse_money(facts.get("sale_price")) or sig.est_value
        if sold_on and (prop.last_sale_date is None or sold_on >= prop.last_sale_date):
            prop.last_sale_date = sold_on
            if price and price > 1000:  # skip $0/$1 family transfers
                prop.last_sale_price = price
    if prop.owner_mailing_address:
        site = normalize_address(prop.address)
        mail = normalize_address(prop.owner_mailing_address)
        prop.absentee = bool(site and mail and site != mail)
    if prop.owner_state and prop.state:
        prop.absentee = prop.absentee or prop.owner_state != prop.state
    estimate_value(prop)


def estimate_value(prop: Property, now: datetime | None = None) -> None:
    now = now or utcnow()
    if prop.last_sale_price and prop.last_sale_date:
        years = max(0.0, (now - prop.last_sale_date).days / 365.25)
        from_sale = prop.last_sale_price * (1 + APPRECIATION) ** years
        prop.est_value = round(max(from_sale, prop.assessed_value or 0))
        prop.mortgage_est = round(remaining_balance(prop.last_sale_price, prop.last_sale_date, now))
    elif prop.assessed_value:
        prop.est_value = round(prop.assessed_value * 1.08)  # assessments typically trail market


def factors(prop: Property, signals: list[Signal], now: datetime | None = None) -> dict[str, bool]:
    now = now or utcnow()
    recent = [s for s in signals if (s.posted_at or s.created_at) >= now - DISTRESS_WINDOW]
    kinds = {s.kind for s in recent}
    tags = {t for s in recent for t in (s.tags or [])}
    out = {k: k in kinds for k in DISTRESS_KINDS}
    out["vacant"] = bool(prop.vacant)
    out["absentee"] = bool(prop.absentee)
    out["out_of_state"] = bool(prop.owner_state and prop.state and prop.owner_state != prop.state)
    out["long_owned"] = bool(prop.last_sale_date and (now - prop.last_sale_date).days >= 15 * 365)
    equity = prop.equity_est
    value = prop.est_value or prop.assessed_value
    out["high_equity"] = bool(equity and value and equity / value >= 0.5)
    out["free_and_clear"] = bool(prop.last_sale_date and (now - prop.last_sale_date).days >= 30 * 365)
    out["expired_listing"] = "re_expired" in tags
    out["damage"] = "fire_water_restoration" in tags
    out["old_house"] = bool(prop.year_built and now.year - prop.year_built >= 50)
    out["prep_permits"] = bool({"painting", "flooring", "roofing"} & tags) and "permit" in kinds
    out["recent_purchase"] = bool(prop.last_sale_date and (now - prop.last_sale_date).days <= 2 * 365)
    return out


def motivation(f: dict[str, bool]) -> int:
    return min(100, sum(w for k, w in MOTIVATION_WEIGHTS.items() if f.get(k)))


def sell_probability(f: dict[str, bool], weights: dict[str, float] | None = None) -> float:
    w = {**SELL_WEIGHTS, **(weights or {})}
    logit = SELL_BASE_LOGIT + sum(v for k, v in w.items() if f.get(k))
    return round(1 / (1 + math.exp(-logit)), 3)


def explain(f: dict[str, bool]) -> list[str]:
    order = list(MOTIVATION_WEIGHTS) + ["prep_permits", "recent_purchase"]
    return [FACTOR_LABELS[k] for k in order if f.get(k)]


def refresh_property(session: Session, prop: Property, weights: dict | None = None) -> None:
    # Shared scores only use public records, never one org's private manual or MLS data.
    signals = session.scalars(select(Signal).where(
        Signal.property_id == prop.id, ~Signal.source_id.like("manual:%"), ~Signal.source_id.like("mls:%"))).all()
    f = factors(prop, signals)
    prop.distress = [k for k in DISTRESS_KINDS if f.get(k)] + [k for k in ("vacant", "absentee") if f.get(k)]
    prop.motivation_score = motivation(f)
    prop.sell_probability = sell_probability(f, weights)
    prop.data = {**(prop.data or {}), "factors": explain(f)}


def refresh_scores(session: Session, signal_ids: list[int]) -> int:
    if not signal_ids:
        return 0
    prop_ids = set(session.scalars(select(Signal.property_id).where(Signal.id.in_(signal_ids),
                                                                   Signal.property_id.is_not(None))))
    from ..intel.learn import load_sell_weights

    weights = load_sell_weights(session)
    for prop in session.scalars(select(Property).where(Property.id.in_(prop_ids))):
        refresh_property(session, prop, weights)
    session.flush()
    return len(prop_ids)
