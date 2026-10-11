"""Predictive "next job" engine: turns one signal into forecast jobs for other trades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .taxonomy import timeline_rules


@dataclass
class Forecast:
    trade: str
    tag: str
    window_start: datetime
    window_end: datetime
    probability: float
    reason: str
    rule: str


def forecast(tags, kind: str, anchor: datetime, *, weights: dict[str, float] | None = None) -> list[Forecast]:
    """All downstream jobs implied by a signal. One forecast per (trade, tag), best rule wins.

    `weights` maps "rule:trade" -> multiplier learned from outcomes (see learn.py).
    """
    tagset = set(tags or [])
    best: dict[tuple[str, str], Forecast] = {}
    for rule in timeline_rules():
        if not (rule.when & tagset):
            continue
        if rule.kinds and kind not in rule.kinds:
            continue
        for nxt in rule.next:
            # A signal that already IS that job for that trade isn't a prediction.
            if nxt.tag in tagset and nxt.start_day <= 0:
                continue
            prob = nxt.probability * (weights or {}).get(f"{rule.name}:{nxt.trade}", 1.0)
            prob = max(0.01, min(0.99, prob))
            fc = Forecast(
                trade=nxt.trade,
                tag=nxt.tag,
                window_start=anchor + timedelta(days=nxt.start_day),
                window_end=anchor + timedelta(days=nxt.end_day),
                probability=round(prob, 3),
                reason=nxt.reason,
                rule=rule.name,
            )
            key = (nxt.trade, nxt.tag)
            if key not in best or best[key].probability < fc.probability:
                best[key] = fc
    return sorted(best.values(), key=lambda f: (f.window_start, -f.probability))
