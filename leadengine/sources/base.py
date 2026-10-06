"""Shared adapter interface and parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx


@dataclass
class RawItem:
    external_id: str
    payload: dict


@dataclass
class LeadInput:
    external_id: str
    kind: str  # permit / bid / request / subdivision / manual
    title: str
    description: str | None = None
    permit_type: str | None = None
    address: str | None = None
    city: str | None = None
    zip: str | None = None
    lat: float | None = None
    lng: float | None = None
    est_value: float | None = None
    owner_name: str | None = None
    contractor_name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    url: str | None = None
    posted_at: datetime | None = None
    due_at: datetime | None = None
    # Hints an adapter can pass to the classifier (e.g. Accela module, use class).
    hints: list[str] = field(default_factory=list)


class Adapter:
    """One adapter per source type. Configured by a sources.yaml entry.

    fetch() pulls raw records changed since `since`; normalize() turns one raw
    payload into a LeadInput (or None to skip it). Keeping them separate lets
    raw payloads be stored and re-normalized later without re-downloading.
    """

    kind: str = "permit"

    def __init__(self, source_id: str, config: dict, client: httpx.Client | None = None):
        self.source_id = source_id
        self.config = config
        self.kind = config.get("kind", self.kind)
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            from ..config import get_settings

            self._client = httpx.Client(
                timeout=60,
                follow_redirects=True,
                headers={"User-Agent": get_settings().user_agent},
            )
        return self._client

    def known(self, external_id: str) -> bool:
        """True if this record was stored on an earlier run (the pipeline overrides this)."""
        return False

    def fetch(self, since: datetime) -> Iterable[RawItem]:  # pragma: no cover - interface
        raise NotImplementedError

    def normalize(self, payload: dict) -> LeadInput | None:  # pragma: no cover - interface
        raise NotImplementedError

    # Default city for sources that cover one jurisdiction.
    @property
    def default_city(self) -> str | None:
        return self.config.get("city")


# ---------------------------------------------------------------- helpers

def pick(record: dict, *candidates: str | list[str] | None) -> Any:
    """Return the first non-empty value among candidate keys (case/format-insensitive).

    Candidates may be strings or lists of strings, so a sources.yaml mapping can
    override the built-in guesses: pick(rec, cfg_fields.get("address"), DEFAULTS).
    """
    lookup = {_norm_key(k): v for k, v in record.items()}
    for cand in candidates:
        if cand is None:
            continue
        for key in [cand] if isinstance(cand, str) else cand:
            value = lookup.get(_norm_key(key))
            if value not in (None, "", " "):
                return value
    return None


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):  # Socrata location objects etc.
        value = value.get("human_address") or value.get("address") or ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


_MONEY_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_money(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = _MONEY_RE.search(str(value).replace("$", ""))
    if not match:
        return None
    try:
        amount = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    return amount if amount > 0 else None


_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%A, %B %d, %Y",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
)


def parse_date(value: Any) -> datetime | None:
    """Parse ISO strings, US dates, RFC-822 and epoch milliseconds (ArcGIS). Returns naive UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.isdigit():
            return parse_date(int(text))
        dt = None
        iso = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            for fmt in _DATE_FORMATS:
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def find_phone(text: str | None) -> str | None:
    if not text:
        return None
    m = _PHONE_RE.search(text)
    return f"({m.group(1)}) {m.group(2)}-{m.group(3)}" if m else None


def find_email(text: str | None) -> str | None:
    if not text:
        return None
    m = _EMAIL_RE.search(text)
    return m.group(0).rstrip(".") if m else None


_DUE_RE = re.compile(
    r"(?:clos(?:e|es|ing)|due|deadline|opening)(?:\s+date)?\s*(?:/\s*time)?\s*[:\-]?\s*"
    r"([A-Z][a-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)


def find_due_date(text: str | None) -> datetime | None:
    if not text:
        return None
    m = _DUE_RE.search(text)
    return parse_date(m.group(1)) if m else None


HAMPTON_ROADS_CITIES = [
    "Virginia Beach", "Chesapeake", "Norfolk", "Portsmouth", "Suffolk", "Hampton",
    "Newport News", "Poquoson", "Williamsburg", "Yorktown", "Smithfield", "Carrollton",
    "Isle of Wight", "James City", "York County", "Gloucester", "Moyock", "Currituck",
]


def find_city(text: str | None) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for city in HAMPTON_ROADS_CITIES:
        if city.lower() in lower:
            return city
    return None
