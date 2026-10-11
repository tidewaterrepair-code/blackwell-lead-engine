"""Steps 2-4: probe each candidate, map its fields, validate on real samples.

The output is always a *declarative* config for an existing, tested adapter
(socrata / arcgis / rss / accela ...). The AI never writes code that runs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from ..db import utcnow
from ..intel.classify import classify
from ..sources import build_adapter
from ..sources.permits_common import DEFAULT_FIELDS
from .discover import Candidate

log = logging.getLogger(__name__)

LOGICAL_FIELDS = ("external_id", "description", "permit_type", "work_type", "address", "city", "zip", "est_value",
                  "owner_name", "contractor_name", "posted_at", "status", "parcel_id", "sale_price", "sale_date",
                  "mailing_address", "assessed_value", "amount_due", "year_built")
ALLOWED_KINDS = ("permit", "violation", "sale", "tax_delinquent", "foreclosure", "probate", "subdivision", "bid")


@dataclass
class Proposal:
    candidate: Candidate
    type: str
    kind: str
    config: dict
    confidence: float
    checks: dict = field(default_factory=dict)
    sample: list = field(default_factory=list)
    problem: str | None = None


def probe(cand: Candidate, client: httpx.Client) -> list[dict]:
    """Fetch up to 25 raw rows from a candidate endpoint."""
    if cand.platform == "socrata":
        resp = client.get(cand.url, params={"$limit": 25, "$order": ":updated_at DESC"})
        resp.raise_for_status()
        return resp.json()
    if cand.platform == "arcgis":
        resp = client.get(cand.url.rstrip("/") + "/query",
                          params={"where": "1=1", "outFields": "*", "f": "json", "resultRecordCount": 25,
                                  "outSR": 4326, "returnGeometry": "true"})
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        rows = []
        for feat in data.get("features", []):
            row = dict(feat.get("attributes") or {})
            geom = feat.get("geometry") or {}
            if "x" in geom:
                row["_lng"], row["_lat"] = geom["x"], geom["y"]
            rows.append(row)
        return rows
    if cand.platform == "rss":
        import feedparser

        resp = client.get(cand.url)
        resp.raise_for_status()
        return [{"title": e.get("title"), "link": e.get("link"), "published": e.get("published")}
                for e in feedparser.parse(resp.content).entries[:25]]
    return []


def heuristic_mapping(columns: list[str]) -> dict[str, str]:
    """Map dataset columns to logical fields using the curated name lists."""
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in columns}
    mapping = {}
    for logical in LOGICAL_FIELDS:
        for cand in DEFAULT_FIELDS.get(logical, []):
            col = norm.get(re.sub(r"[^a-z0-9]", "", cand.lower()))
            if col and col not in mapping.values():
                mapping[logical] = col
                break
    return mapping


MAP_SYSTEM = """You map columns of a government open-data dataset to a lead-generation schema. Choose the dataset \
kind and, for each logical field, the single best matching column name exactly as given, or null. Base the choice \
on the column names and the sample rows. date_field must be a column holding the record's main date."""


def ai_mapping(cand: Candidate, columns: list[str], rows: list[dict]) -> dict | None:
    from ..intel.ai import ask_json

    col_enum = [*columns, None]
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "fields", "date_field", "confidence"],
        "properties": {
            "kind": {"type": "string", "enum": list(ALLOWED_KINDS)},
            "fields": {"type": "object", "additionalProperties": False, "required": list(LOGICAL_FIELDS),
                       "properties": {f: {"enum": col_enum} for f in LOGICAL_FIELDS}},
            "date_field": {"enum": col_enum},
            "confidence": {"type": "number"},
        },
    }
    sample = [{k: (str(v)[:80] if v is not None else None) for k, v in r.items()} for r in rows[:5]]
    user = f"Dataset title: {cand.title}\nGuessed kind: {cand.kind}\nColumns: {columns}\nSample rows: {sample}"
    return ask_json(MAP_SYSTEM, user, schema, effort="low", max_tokens=2000)


def _config_for(cand: Candidate, kind: str, mapping: dict, date_field: str | None, county: dict) -> tuple[str, dict]:
    base = {"state": county["state"], "county_fips": county["fips"], "jurisdiction": county["fips"],
            "fields": {k: v for k, v in mapping.items() if v}}
    if cand.platform == "socrata":
        cfg = {**base, "domain": cand.domain or re.sub(r"^https://([^/]+)/.*$", r"\1", cand.url),
               "dataset": cand.dataset or re.sub(r"^.*/resource/([a-z0-9-]+)\.json.*$", r"\1", cand.url)}
        if date_field:
            cfg["date_field"] = date_field
        return "socrata", cfg
    if cand.platform == "arcgis":
        cfg = {**base, "url": cand.url}
        if date_field:
            cfg["date_field"] = date_field
        return "arcgis", cfg
    if cand.platform == "rss":
        return "rss", {"url": cand.url, "state": county["state"], "county_fips": county["fips"],
                       "jurisdiction": county["fips"]}
    if cand.platform == "accela":
        m = re.match(r"(https://[^/]+/[A-Za-z0-9_]+)", cand.url)
        return "accela", {"base_url": m.group(1) if m else cand.url, "module": "Building", "state": county["state"],
                          "county_fips": county["fips"], "jurisdiction": county["fips"]}
    return cand.platform, {"url": cand.url, **base}


def build_proposal(cand: Candidate, county: dict, client: httpx.Client) -> Proposal:
    kind = cand.kind if cand.kind in ALLOWED_KINDS else "permit"
    if cand.platform in ("accela",):
        stype, cfg = _config_for(cand, kind, {}, None, county)
        return Proposal(cand, stype, kind, cfg, 0.4, {"needs_browser": True},
                        problem="Browser portal: test with `pegasus inspect` after approval")
    if cand.platform not in ("socrata", "arcgis", "rss"):
        return Proposal(cand, cand.platform, kind, {"url": cand.url}, 0.1, problem="No automatic adapter for this platform")
    try:
        rows = probe(cand, client)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return Proposal(cand, cand.platform, kind, {}, 0.0, problem=f"Probe failed: {exc}")
    if not rows:
        return Proposal(cand, cand.platform, kind, {}, 0.0, problem="No rows returned")
    columns = sorted({k for r in rows for k in r.keys()})
    date_field = None
    if cand.platform == "rss":
        mapping = {}
    else:
        mapping = heuristic_mapping(columns)
        ai = ai_mapping(cand, columns, rows)
        if ai:
            kind = ai.get("kind") if ai.get("kind") in ALLOWED_KINDS else kind
            for k, v in (ai.get("fields") or {}).items():
                if v in columns:
                    mapping[k] = v
            date_field = ai.get("date_field") if ai.get("date_field") in columns else None
        date_field = date_field or mapping.get("posted_at") or mapping.get("sale_date")
    stype, cfg = _config_for(cand, kind, mapping, date_field, county)
    return validate(Proposal(cand, stype, kind, cfg, 0.0), rows)


def validate(prop: Proposal, rows: list[dict]) -> Proposal:
    """Run the real adapter's normalize() on the sample and score the result."""
    adapter = build_adapter("scout-preview", {**prop.config, "type": prop.type, "kind": prop.kind})
    items = [adapter.apply_defaults(adapter.normalize(r)) for r in rows]
    items = [i for i in items if i is not None]
    n = len(rows)
    if not items:
        prop.problem, prop.confidence = "Nothing could be normalized from the sample", 0.0
        return prop
    fill = lambda attr: round(sum(1 for i in items if getattr(i, attr)) / len(items), 2)  # noqa: E731
    dates = [i.posted_at for i in items if i.posted_at]
    newest = max(dates) if dates else None
    fresh_days = (utcnow() - newest).days if newest else None
    relevant = sum(1 for i in items if classify(kind=i.kind, title=i.title, description=i.description,
                                                permit_type=i.permit_type, hints=i.hints).relevant)
    checks = {
        "normalized": round(len(items) / n, 2), "address": fill("address"), "date": fill("posted_at"),
        "location": round(sum(1 for i in items if i.lat or i.zip or i.city) / len(items), 2),
        "relevant": round(relevant / len(items), 2), "freshest_days": fresh_days,
    }
    conf = (0.25 * checks["normalized"] + 0.2 * checks["address"] + 0.2 * checks["date"] + 0.15 * checks["location"]
            + 0.2 * min(1.0, checks["relevant"] * 2))
    if fresh_days is None or fresh_days > 120:
        conf *= 0.5
        prop.problem = "Data looks stale (no records in the last 120 days)"
    prop.confidence, prop.checks = round(conf, 2), checks
    prop.sample = [{"title": i.title, "address": i.address, "posted_at": i.posted_at.isoformat() if i.posted_at else None,
                    "value": i.est_value} for i in items[:5]]
    return prop
