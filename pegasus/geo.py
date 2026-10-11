"""Territory geometry: radius, ZIP, county, city and drawn polygons. Pure Python, no PostGIS."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from .intel.scoring import miles_between

MILES_PER_DEG_LAT = 69.0


def radius_bbox(lat: float, lng: float, miles: float) -> tuple[float, float, float, float]:
    dlat = miles / MILES_PER_DEG_LAT
    dlng = miles / (MILES_PER_DEG_LAT * max(0.01, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def _rings(geojson: dict) -> list[list[list[list[float]]]]:
    """Normalize a GeoJSON Polygon/MultiPolygon/Feature into a list of polygons (lists of rings)."""
    if geojson.get("type") == "Feature":
        geojson = geojson["geometry"]
    if geojson.get("type") == "FeatureCollection":
        out = []
        for feat in geojson.get("features", []):
            out.extend(_rings(feat))
        return out
    if geojson.get("type") == "Polygon":
        return [geojson["coordinates"]]
    if geojson.get("type") == "MultiPolygon":
        return list(geojson["coordinates"])
    raise ValueError("territory polygon must be a GeoJSON Polygon or MultiPolygon")


def _in_ring(lat: float, lng: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geojson(lat: float, lng: float, geojson: dict) -> bool:
    for polygon in _rings(geojson):
        if not polygon:
            continue
        if _in_ring(lat, lng, polygon[0]) and not any(_in_ring(lat, lng, hole) for hole in polygon[1:]):
            return True
    return False


def polygon_bbox(geojson: dict) -> tuple[float, float, float, float]:
    lats, lngs = [], []
    for polygon in _rings(geojson):
        for lng, lat, *_ in polygon[0]:
            lats.append(lat)
            lngs.append(lng)
    return min(lats), max(lats), min(lngs), max(lngs)


def territory_bbox(kind: str, data: dict):
    if kind == "radius":
        return radius_bbox(float(data["lat"]), float(data["lng"]), float(data["miles"]))
    if kind == "polygon":
        return polygon_bbox(data["geojson"])
    return None


def validate_territory(kind: str, data: dict) -> dict:
    """Clean and validate territory data from the API. Raises ValueError."""
    if kind == "radius":
        lat, lng, miles = float(data["lat"]), float(data["lng"]), float(data["miles"])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180) or not (0 < miles <= 150):
            raise ValueError("radius must be 1-150 miles around a valid point")
        return {"lat": lat, "lng": lng, "miles": miles, "label": data.get("label")}
    if kind == "zip":
        zips = sorted({str(z).strip()[:5] for z in data.get("zips", []) if str(z).strip()[:5].isdigit()})
        if not zips:
            raise ValueError("add at least one 5-digit ZIP code")
        return {"zips": zips}
    if kind == "county":
        fips = sorted({str(f).strip() for f in data.get("fips", []) if str(f).strip().isdigit()})
        if not fips:
            raise ValueError("add at least one county FIPS code")
        return {"fips": fips, "names": data.get("names", [])}
    if kind == "city":
        city, state = (data.get("city") or "").strip(), (data.get("state") or "").strip().upper()[:2]
        if not city:
            raise ValueError("city is required")
        return {"city": city, "state": state}
    if kind == "polygon":
        geojson = data.get("geojson") or {}
        polygon_bbox(geojson)  # validates shape
        return {"geojson": geojson}
    raise ValueError(f"unknown territory kind {kind!r}")


@dataclass
class Located:
    """The location facts of a signal or property used for territory matching."""

    lat: float | None
    lng: float | None
    zip: str | None
    county_fips: str | None
    city: str | None
    state: str | None
    radius_miles: float | None = None


def territory_contains(kind: str, data: dict, loc: Located) -> bool:
    if kind == "radius":
        if loc.lat is None or loc.lng is None:
            return False
        reach = float(data["miles"]) + (loc.radius_miles or 0)
        return miles_between(loc.lat, loc.lng, float(data["lat"]), float(data["lng"])) <= reach
    if kind == "polygon":
        if loc.lat is None or loc.lng is None:
            return False
        if loc.radius_miles:  # area signal: test center or any bbox corner within reach
            if point_in_geojson(loc.lat, loc.lng, data["geojson"]):
                return True
            s, n, w, e = radius_bbox(loc.lat, loc.lng, loc.radius_miles)
            return any(point_in_geojson(a, b, data["geojson"]) for a, b in ((s, w), (s, e), (n, w), (n, e)))
        return point_in_geojson(loc.lat, loc.lng, data["geojson"])
    if kind == "zip":
        return bool(loc.zip) and loc.zip[:5] in data.get("zips", [])
    if kind == "county":
        return bool(loc.county_fips) and loc.county_fips in data.get("fips", [])
    if kind == "city":
        if not loc.city or loc.city.strip().lower() != data.get("city", "").lower():
            return False
        return not (data.get("state") and loc.state) or data["state"].upper() == loc.state.upper()
    return False


class TerritoryIndex:
    """In-memory index over all territories, rebuilt once per ingest run."""

    def __init__(self, territories):
        self.by_zip: dict[str, list] = defaultdict(list)
        self.by_fips: dict[str, list] = defaultdict(list)
        self.by_city: dict[str, list] = defaultdict(list)
        self.spatial: list = []
        for t in territories:
            if t.kind == "zip":
                for z in t.data.get("zips", []):
                    self.by_zip[z].append(t)
            elif t.kind == "county":
                for f in t.data.get("fips", []):
                    self.by_fips[f].append(t)
            elif t.kind == "city":
                self.by_city[t.data.get("city", "").lower()].append(t)
            else:
                self.spatial.append(t)

    def candidates(self, loc: Located) -> list:
        out = []
        if loc.zip:
            out += self.by_zip.get(loc.zip[:5], [])
        if loc.county_fips:
            out += self.by_fips.get(loc.county_fips, [])
        if loc.city:
            out += self.by_city.get(loc.city.lower(), [])
        if loc.lat is not None and loc.lng is not None:
            pad = (loc.radius_miles or 0) / MILES_PER_DEG_LAT * 1.5
            for t in self.spatial:
                if t.min_lat is None:
                    continue
                if (t.min_lat - pad <= loc.lat <= t.max_lat + pad
                        and t.min_lng - pad * 1.3 <= loc.lng <= t.max_lng + pad * 1.3):
                    out.append(t)
        seen, unique = set(), []
        for t in out:
            if t.id not in seen and territory_contains(t.kind, t.data, loc):
                seen.add(t.id)
                unique.append(t)
        return unique
