"""Lead scoring (0-100), distance math and dedupe keys.

A score is computed per org: the same permit is worth more to the deck
builder 4 miles away than to the one 40 miles away.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime

from ..db import utcnow


def value_points(value: float | None) -> int:
    if value is None:
        return 8
    for threshold, points in ((250_000, 25), (100_000, 20), (50_000, 15), (20_000, 10), (5_000, 5)):
        if value >= threshold:
            return points
    return 2


def recency_points(posted_at: datetime | None, now: datetime) -> int:
    if posted_at is None:
        return 8
    age = (now - posted_at).days
    for days, points in ((3, 20), (7, 15), (14, 10), (30, 5)):
        if age <= days:
            return points
    return 0


def window_points(start: datetime, end: datetime, now: datetime) -> int:
    """Predicted jobs: highest when the window is open now or about to open."""
    if end < now:
        return 0
    if start <= now:
        return 20
    days_out = (start - now).days
    for days, points in ((14, 17), (30, 13), (60, 9), (120, 5)):
        if days_out <= days:
            return points
    return 2


def miles_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_points(lat, lng, base_lat, base_lng) -> int:
    if None in (lat, lng, base_lat, base_lng):
        return 7
    miles = miles_between(lat, lng, base_lat, base_lng)
    for limit, points in ((10, 15), (25, 10), (40, 5)):
        if miles <= limit:
            return points
    return 0


@dataclass
class ScoreInput:
    kind: str
    est_value: float | None
    posted_at: datetime | None
    lat: float | None = None
    lng: float | None = None
    due_at: datetime | None = None
    contractor_listed: bool = False
    commercial: bool = False
    customer_type: str = "homeowner"
    trade_group: str = "trades"
    commercial_ok: bool = False
    # Predictions
    window_start: datetime | None = None
    window_end: datetime | None = None
    probability: float | None = None
    # Real estate
    motivation: int | None = None
    default_ticket: float | None = None
    learned_weight: float = 1.0


@dataclass
class Score:
    value: int
    reasons: list[str] = field(default_factory=list)


def score(inp: ScoreInput, *, base_lat=None, base_lng=None, now: datetime | None = None) -> Score:
    now = now or utcnow()
    reasons: list[str] = []
    predicted = inp.window_start is not None and inp.window_end is not None

    # 1. How directly this is a job for the trade.
    if predicted:
        prob = inp.probability or 0.3
        points = round(10 + 20 * prob)
        reasons.append(f"{round(prob * 100)}% likely")
    else:
        points = 30

    # 2. Job size.
    value = inp.est_value
    if value is None and inp.default_ticket:
        points += value_points(inp.default_ticket) // 2 + 3
    else:
        points += value_points(value)
        if value and value >= 100_000:
            reasons.append(f"${value / 1000:,.0f}k job")

    # 3. Timing.
    if predicted:
        points += window_points(inp.window_start, inp.window_end, now)
        if inp.window_start <= now <= inp.window_end:
            reasons.append("Window open now")
    else:
        rp = recency_points(inp.posted_at, now)
        points += rp
        if rp >= 15:
            reasons.append("Fresh")

    # 4. Distance from the customer's base.
    dp = distance_points(inp.lat, inp.lng, base_lat, base_lng)
    points += dp
    if dp >= 15:
        reasons.append("Close by")

    # 5. Situation bonuses and penalties.
    if inp.kind == "permit" and inp.customer_type == "homeowner" and not inp.contractor_listed and not predicted:
        points += 10
        reasons.append("No contractor yet")
    if inp.kind == "request":
        points += 10
        reasons.append("Asking for help")
    if inp.kind == "bid" and inp.due_at is not None:
        if inp.due_at < now:
            return Score(0, ["Closed"])
        points += 5
        days = (inp.due_at - now).days
        reasons.append(f"Due in {days}d" if days > 0 else "Due today")
    if inp.commercial and not inp.commercial_ok and inp.kind != "bid":
        points -= 10
    if inp.trade_group == "realestate" and inp.motivation is not None:
        # Motivation (distress stack) dominates for agents and investors.
        points = round(points * 0.55 + inp.motivation * 0.45)
        if inp.motivation >= 70:
            reasons.append("Highly motivated")

    points = round(points * inp.learned_weight)
    return Score(max(0, min(100, int(points))), reasons[:4])


_ADDR_ABBR = {
    "street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "lane": "ln", "court": "ct",
    "boulevard": "blvd", "circle": "cir", "place": "pl", "parkway": "pkwy", "terrace": "ter",
    "highway": "hwy", "north": "n", "south": "s", "east": "e", "west": "w", "trail": "trl",
    "landing": "lndg", "point": "pt", "crescent": "cres", "square": "sq", "way": "way",
}
_UNIT_RE = re.compile(r"\b(apt|unit|ste|suite|#|lot|bldg|building)\b.*$")


def normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    text = address.lower().split(",")[0]
    text = _UNIT_RE.sub("", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    words = [_ADDR_ABBR.get(w, w) for w in text.split()]
    out = " ".join(words).strip()
    return out or None


def dedupe_key(address: str | None, job_type: str) -> str | None:
    norm = normalize_address(address)
    if not norm or not re.match(r"^\d", norm):  # needs a street number to be meaningful
        return None
    return f"{norm}|{job_type}"
