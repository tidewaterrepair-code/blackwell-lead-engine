"""Lead scoring (0-100) and dedupe keys."""

from __future__ import annotations

import math
import re
from datetime import datetime

from .db import utcnow

JOB_WEIGHT = {
    "new_construction": 30,
    "house_framing": 30,
    "addition": 28,
    "garage_framing": 25,
    "deck": 25,
    "kitchen": 25,
    "bath": 22,
    "remodel": 15,
    "other": 0,
}


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


def score_lead(
    *,
    job_type: str,
    kind: str,
    customer_type: str,
    est_value: float | None,
    posted_at: datetime | None,
    due_at: datetime | None = None,
    lat: float | None = None,
    lng: float | None = None,
    base_lat: float | None = None,
    base_lng: float | None = None,
    contractor_listed: bool = False,
    commercial: bool = False,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    if job_type == "other":
        return 0
    score = JOB_WEIGHT.get(job_type, 0)
    score += value_points(est_value)
    score += recency_points(posted_at, now)
    score += distance_points(lat, lng, base_lat, base_lng)
    if kind == "permit" and customer_type == "homeowner" and not contractor_listed:
        score += 10  # owner pulled it / nobody hired yet
    if kind == "request":
        score += 10  # someone is actively asking for a contractor
    if kind == "bid" and due_at is not None:
        if due_at < now:
            return 0
        score += 5
    if commercial and kind != "bid":
        score -= 10
    return max(0, min(100, int(score)))


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
