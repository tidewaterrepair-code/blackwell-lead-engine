"""The learning loop: re-weights predictions and likely-to-sell from real outcomes.

Runs nightly. Uses Bayesian smoothing so a handful of outcomes nudges the
priors instead of overwriting them; with lots of evidence the data wins.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Listing, ModelParam, OrgLead, Prediction, Property, Signal

PRIOR_STRENGTH = 20  # pseudo-observations behind each prior
POSITIVE = ("won", "quoted", "contacted")
NEGATIVE = ("lost", "passed")


def _get(session: Session, key: str) -> dict:
    row = session.get(ModelParam, key)
    return dict(row.value) if row else {}


def _put(session: Session, key: str, value: dict) -> None:
    row = session.get(ModelParam, key)
    if row is None:
        session.add(ModelParam(key=key, value=value))
    else:
        row.value = value
        row.updated_at = utcnow()


def load_weights(session: Session) -> dict[str, float]:
    return {k: float(v) for k, v in _get(session, "timeline_weights").get("weights", {}).items()}


def load_sell_weights(session: Session) -> dict[str, float]:
    return {k: float(v) for k, v in _get(session, "sell_weights").get("weights", {}).items()}


def learn_timelines(session: Session) -> dict:
    """Per rule:trade, compare engagement on predicted leads with the prior probability.

    A prediction lead counts as a hit when the customer contacted, quoted or won it,
    and as a miss when they passed or lost it. weight = posterior / prior.
    """
    stats: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])  # hits, misses, prior
    rows = session.execute(
        select(Prediction.rule, Prediction.trade, Prediction.probability, OrgLead.status)
        .join(OrgLead, OrgLead.prediction_id == Prediction.id)
        .where(OrgLead.status.in_(POSITIVE + NEGATIVE), Prediction.rule.is_not(None))
    ).all()
    for rule, trade, prob, status in rows:
        key = f"{rule}:{trade}"
        st = stats[key]
        st[0 if status in POSITIVE else 1] += 1
        st[2] = prob
    weights, report = {}, {}
    for key, (hits, misses, prior) in stats.items():
        prior = max(0.01, min(0.99, prior))
        alpha, beta = prior * PRIOR_STRENGTH + hits, (1 - prior) * PRIOR_STRENGTH + misses
        posterior = alpha / (alpha + beta)
        weights[key] = round(max(0.25, min(3.0, posterior / prior)), 3)
        report[key] = {"hits": hits, "misses": misses, "prior": prior, "posterior": round(posterior, 3)}
    _put(session, "timeline_weights", {"weights": weights, "report": report, "at": utcnow().isoformat()})
    return report


def learn_sell_weights(session: Session) -> dict:
    """Calibrate likely-to-sell factor weights from MLS listings matched to properties.

    Label: the property was listed within 365 days after the factor was observed.
    Each factor's log-odds ratio is shrunk toward the prior by evidence size.
    """
    from ..realestate.properties import SELL_WEIGHTS, factors

    cutoff = utcnow() - timedelta(days=365)
    listed = set(session.scalars(select(Listing.property_id).where(Listing.property_id.is_not(None),
                                                                   Listing.list_date >= cutoff)))
    props = session.scalars(select(Property).where(Property.updated_at <= utcnow())).all()
    if len(listed) < 30:
        return {"skipped": "need at least 30 matched listings", "matched": len(listed)}
    counts = {k: [0, 0, 0, 0] for k in SELL_WEIGHTS}  # with&listed, with, without&listed, without
    signals_by_prop: dict[int, list] = defaultdict(list)
    for sig in session.scalars(select(Signal).where(Signal.property_id.in_([p.id for p in props]))):
        signals_by_prop[sig.property_id].append(sig)
    for prop in props:
        f = factors(prop, signals_by_prop.get(prop.id, []), now=cutoff + timedelta(days=1))
        y = prop.id in listed
        for k in counts:
            if f.get(k):
                counts[k][0] += y
                counts[k][1] += 1
            else:
                counts[k][2] += y
                counts[k][3] += 1
    weights, report = {}, {}
    for k, (wl, w, ol, o) in counts.items():
        if w < 5 or o < 5:
            continue
        p1, p0 = (wl + 0.5) / (w + 1), (ol + 0.5) / (o + 1)
        observed = math.log(p1 / (1 - p1)) - math.log(p0 / (1 - p0))
        trust = w / (w + PRIOR_STRENGTH)
        weights[k] = round(trust * observed + (1 - trust) * SELL_WEIGHTS[k], 3)
        report[k] = {"with": w, "rate_with": round(p1, 3), "rate_without": round(p0, 3), "weight": weights[k]}
    _put(session, "sell_weights", {"weights": weights, "report": report, "at": utcnow().isoformat()})
    return report


def nightly(session: Session) -> dict:
    return {"timelines": learn_timelines(session), "sell": learn_sell_weights(session)}
