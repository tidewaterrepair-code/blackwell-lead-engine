"""Free geocoding with the US Census Bureau geocoder (no API key, cached in the DB)."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import GeocodeCache, Lead

log = logging.getLogger(__name__)

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def full_address(lead: Lead) -> str | None:
    if not lead.address:
        return None
    parts = [lead.address]
    if lead.city and lead.city.lower() not in lead.address.lower():
        parts.append(lead.city)
    if " va" not in lead.address.lower():
        parts.append("VA")
    if lead.zip:
        parts.append(lead.zip)
    return ", ".join(parts)


def census_lookup(address: str, client: httpx.Client) -> tuple[float | None, float | None]:
    resp = client.get(
        CENSUS_URL,
        params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    matches = resp.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None, None
    coords = matches[0]["coordinates"]
    return float(coords["y"]), float(coords["x"])


def geocode_missing(session: Session, client: httpx.Client | None = None, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.geocode_enabled:
        return 0
    limit = limit if limit is not None else settings.geocode_per_run
    leads = session.scalars(
        select(Lead)
        .where(
            Lead.lat.is_(None),
            Lead.geocode_tried.is_(False),
            Lead.address.is_not(None),
            Lead.duplicate_of_id.is_(None),
        )
        .order_by(Lead.score.desc())
        .limit(limit)
    ).all()
    if not leads:
        return 0
    own_client = client is None
    client = client or httpx.Client(headers={"User-Agent": settings.user_agent})
    done = 0
    try:
        for lead in leads:
            address = full_address(lead)
            if not address:
                lead.geocode_tried = True
                continue
            cached = session.get(GeocodeCache, address)
            if cached is None:
                try:
                    lat, lng = census_lookup(address, client)
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    log.warning("geocode failed for %s: %s", address, exc)
                    break  # service down; try again next run
                cached = GeocodeCache(address=address, lat=lat, lng=lng)
                session.add(cached)
            lead.geocode_tried = True
            if cached.lat is not None:
                lead.lat, lead.lng = cached.lat, cached.lng
                done += 1
        session.flush()
    finally:
        if own_client:
            client.close()
    return done
