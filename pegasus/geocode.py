"""Free geocoding with the US Census Bureau geocoder (no API key, cached in the DB).

The "geographies" endpoint returns coordinates plus the county FIPS and ZIP,
which is exactly what territory matching needs.
"""

from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import GeocodeCache, Signal

log = logging.getLogger(__name__)

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"


def full_address(sig: Signal) -> str | None:
    if not sig.address or not re.match(r"^\s*\d", sig.address):
        return None
    parts = [sig.address]
    lower = sig.address.lower()
    if sig.city and sig.city.lower() not in lower:
        parts.append(sig.city)
    if sig.state and f" {sig.state.lower()}" not in lower:
        parts.append(sig.state)
    if sig.zip and sig.zip not in sig.address:
        parts.append(sig.zip)
    return ", ".join(parts)


def census_lookup(address: str, client: httpx.Client) -> dict | None:
    resp = client.get(CENSUS_URL, params={
        "address": address, "benchmark": "Public_AR_Current", "vintage": "Current_Current",
        "layers": "Counties", "format": "json"}, timeout=30)
    resp.raise_for_status()
    matches = resp.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    county = (m.get("geographies", {}).get("Counties") or [{}])[0]
    zip_match = re.search(r"\b(\d{5})\s*$", m.get("matchedAddress", ""))
    return {
        "lat": float(m["coordinates"]["y"]),
        "lng": float(m["coordinates"]["x"]),
        "county_fips": county.get("GEOID"),
        "zip": zip_match.group(1) if zip_match else None,
    }


def geocode_missing(session: Session, client: httpx.Client | None = None, limit: int | None = None) -> list[int]:
    """Geocode signals that have a street address but no coordinates. Returns updated signal ids."""
    settings = get_settings()
    if not settings.geocode_enabled:
        return []
    limit = limit if limit is not None else settings.geocode_per_run
    sigs = session.scalars(
        select(Signal).where(Signal.lat.is_(None), Signal.geocode_tried.is_(False), Signal.address.is_not(None),
                             Signal.duplicate_of_id.is_(None))
        .order_by(Signal.created_at.desc()).limit(limit)
    ).all()
    if not sigs:
        return []
    own_client = client is None
    client = client or httpx.Client(headers={"User-Agent": settings.user_agent})
    updated: list[int] = []
    try:
        for sig in sigs:
            address = full_address(sig)
            sig.geocode_tried = True
            if not address:
                continue
            cached = session.get(GeocodeCache, address)
            if cached is None:
                try:
                    hit = census_lookup(address, client)
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    log.warning("geocode failed for %s: %s", address, exc)
                    sig.geocode_tried = False
                    break  # service down; try again next run
                cached = GeocodeCache(address=address, lat=hit and hit["lat"], lng=hit and hit["lng"],
                                      county_fips=hit and hit["county_fips"], zip=hit and hit["zip"])
                session.add(cached)
            if cached.lat is not None:
                sig.lat, sig.lng = cached.lat, cached.lng
                sig.county_fips = sig.county_fips or cached.county_fips
                sig.zip = sig.zip or cached.zip
                if sig.property and sig.property.lat is None:
                    sig.property.lat, sig.property.lng = cached.lat, cached.lng
                updated.append(sig.id)
        session.flush()
    finally:
        if own_client:
            client.close()
    return updated
