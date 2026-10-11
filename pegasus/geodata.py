"""Bundled US reference data: counties (FIPS, centroid, bbox) and ZIP codes.

Built from free datasets by scripts/build_geodata.mjs (us-atlas + zipcodes npm packages).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

DATA = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def counties() -> dict[str, dict]:
    rows = json.loads((DATA / "us_counties.json").read_text())
    return {r["fips"]: r for r in rows}


@lru_cache(maxsize=1)
def zips() -> dict[str, list]:
    return json.loads((DATA / "us_zips.json").read_text())


def county(fips: str) -> dict | None:
    return counties().get(fips)


def county_label(fips: str) -> str:
    c = county(fips)
    if not c:
        return fips
    name = c["name"]
    if c["state"] == "VA" and fips[2] in "5678" and int(fips[2:]) >= 510:
        return f"{name} (city), {c['state']}"  # Virginia independent cities
    suffix = "" if any(w in name for w in ("Parish", "Borough", "Census Area", "city")) else " County"
    return f"{name}{suffix}, {c['state']}"


def zip_info(code: str) -> dict | None:
    row = zips().get((code or "")[:5])
    if not row:
        return None
    city, state, lat, lng, fips = row
    return {"zip": code[:5], "city": city, "state": state, "lat": lat, "lng": lng, "county_fips": fips}


@lru_cache(maxsize=1)
def _city_index() -> dict[tuple[str, str], list[str]]:
    idx: dict[tuple[str, str], list[str]] = defaultdict(list)
    for code, (city, state, *_rest) in zips().items():
        idx[(city.lower(), state)].append(code)
    return idx


def city_zips(city: str, state: str) -> list[str]:
    return _city_index().get((city.strip().lower(), state.strip().upper()), [])


def city_county(city: str, state: str) -> str | None:
    fips = [zips()[z][4] for z in city_zips(city, state) if zips()[z][4]]
    return Counter(fips).most_common(1)[0][0] if fips else None


def locate_point(lat: float, lng: float) -> str | None:
    """Best-guess county for a point: nearest centroid among counties whose bbox contains it."""
    best, best_d = None, None
    for c in counties().values():
        s, n, w, e = c["bbox"]
        if s <= lat <= n and w <= lng <= e:
            d = (c["lat"] - lat) ** 2 + (c["lng"] - lng) ** 2
            if best_d is None or d < best_d:
                best, best_d = c["fips"], d
    return best


def search(query: str, limit: int = 12) -> list[dict]:
    """Search counties, cities and ZIPs for the area picker."""
    q = query.strip().lower()
    if not q:
        return []
    out: list[dict] = []
    if q[:5].isdigit():
        info = zip_info(q[:5])
        if info:
            out.append({"type": "zip", "id": info["zip"], "label": f"{info['zip']} · {info['city']}, {info['state']}",
                        "lat": info["lat"], "lng": info["lng"], "county_fips": info["county_fips"]})
        return out
    state = None
    if "," in q:
        q, state = (p.strip() for p in q.split(",", 1))
        state = state.upper()[:2] or None
    for (city, st), codes in _city_index().items():
        if city.startswith(q) and (state is None or st == state):
            first = zips()[codes[0]]
            out.append({"type": "city", "id": f"{first[0]}|{st}", "label": f"{first[0]}, {st}",
                        "lat": first[2], "lng": first[3], "zips": len(codes), "county_fips": city_county(city, st)})
            if len(out) >= limit // 2:
                break
    for c in counties().values():
        if c["name"].lower().startswith(q) and (state is None or c["state"] == state):
            out.append({"type": "county", "id": c["fips"], "label": county_label(c["fips"]),
                        "lat": c["lat"], "lng": c["lng"]})
            if len(out) >= limit:
                break
    return out[:limit]


def ensure_jurisdiction(session: Session, fips: str):
    """Get or create the jurisdiction row for a county FIPS code."""
    from .models import Jurisdiction

    j = session.get(Jurisdiction, fips)
    if j is None:
        c = county(fips)
        if c is None:
            raise ValueError(f"unknown county FIPS {fips}")
        j = Jurisdiction(id=fips, name=county_label(fips), state=c["state"], kind="county",
                         lat=c["lat"], lng=c["lng"], coverage="none", coverage_kinds=[])
        session.add(j)
        session.flush()
    return j


def territory_counties(kind: str, data: dict) -> set[str]:
    """Which counties a territory touches (drives coverage checks and Source Scout)."""
    if kind == "county":
        return set(data.get("fips", []))
    if kind == "zip":
        return {zips()[z][4] for z in data.get("zips", []) if z in zips() and zips()[z][4]}
    if kind == "city":
        fips = city_county(data.get("city", ""), data.get("state", ""))
        return {fips} if fips else set()
    if kind == "radius":
        from .geo import radius_bbox
        from .intel.scoring import miles_between

        lat, lng, miles = float(data["lat"]), float(data["lng"]), float(data["miles"])
        s, n, w, e = radius_bbox(lat, lng, miles)
        out = set()
        for c in counties().values():
            cs, cn, cw, ce = c["bbox"]
            if cn < s or cs > n or ce < w or cw > e:
                continue
            # Keep counties whose centroid or nearest bbox point is within the radius.
            near_lat = min(max(lat, cs), cn)
            near_lng = min(max(lng, cw), ce)
            if miles_between(lat, lng, near_lat, near_lng) <= miles:
                out.add(c["fips"])
        return out
    if kind == "polygon":
        from .geo import point_in_geojson, polygon_bbox

        s, n, w, e = polygon_bbox(data["geojson"])
        out = set()
        for c in counties().values():
            cs, cn, cw, ce = c["bbox"]
            if cn < s or cs > n or ce < w or cw > e:
                continue
            if point_in_geojson(c["lat"], c["lng"], data["geojson"]) or (cs <= (s + n) / 2 <= cn and cw <= (w + e) / 2 <= ce):
                out.add(c["fips"])
        return out
    return set()
