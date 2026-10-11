"""Step 1: discover candidate public data sources for a county.

Three free discovery channels, combined:
  * Socrata Discovery API (open-data catalogs on Socrata)
  * ArcGIS Hub search (city/county GIS open-data sites)
  * Claude with web search (official permit portals, treasurer tax lists,
    planning agendas, bid boards) when ANTHROPIC_API_KEY is set
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

SOCRATA_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
ARCGIS_HUB = "https://hub.arcgis.com/api/search/v1/collections/dataset/items"
TOPICS = {
    "permit": ["building permits", "permits issued", "permit applications"],
    "violation": ["code enforcement", "code violations"],
    "sale": ["real estate sales", "property sales", "property transfers"],
    "tax_delinquent": ["delinquent taxes", "tax delinquent"],
}


@dataclass
class Candidate:
    platform: str  # socrata / arcgis / accela / rss / html_list / agenda_pdf / csv / unknown
    kind: str
    title: str
    url: str
    domain: str | None = None
    dataset: str | None = None
    columns: list[str] | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _place_words(county: dict) -> list[str]:
    name = county["name"].lower()
    return [w for w in re.split(r"[^a-z]+", name) if len(w) > 2]


def socrata_candidates(county: dict, client: httpx.Client) -> list[Candidate]:
    out = []
    words = _place_words(county)
    for kind, terms in TOPICS.items():
        for term in terms[:2]:
            try:
                resp = client.get(SOCRATA_CATALOG, params={"q": f"{county['name']} {term}", "only": "datasets",
                                                           "limit": 10})
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.info("socrata discovery failed: %s", exc)
                return out
            for r in resp.json().get("results", []):
                res, meta = r.get("resource", {}), r.get("metadata", {})
                domain = meta.get("domain", "")
                haystack = f"{domain} {res.get('name', '')} {res.get('description', '')}".lower()
                if not any(w in haystack for w in words):
                    continue
                out.append(Candidate("socrata", kind, res.get("name", ""), f"https://{domain}/resource/{res.get('id')}.json",
                                     domain=domain, dataset=res.get("id"), columns=res.get("columns_field_name")))
    return out


def arcgis_candidates(county: dict, client: httpx.Client) -> list[Candidate]:
    out = []
    s, n, w, e = county["bbox"]
    for kind, terms in TOPICS.items():
        try:
            resp = client.get(ARCGIS_HUB, params={"q": terms[0], "bbox": f"{w},{s},{e},{n}", "limit": 10})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.info("arcgis hub discovery failed: %s", exc)
            return out
        for feat in resp.json().get("features", []):
            props = feat.get("properties", {})
            url = props.get("url") or ""
            if "FeatureServer" not in url and "MapServer" not in url:
                continue
            if not re.search(r"/(FeatureServer|MapServer)/\d+$", url):
                url = url.rstrip("/") + "/0"
            out.append(Candidate("arcgis", kind, props.get("title", ""), url, domain=props.get("source")))
    return out


RESEARCH_SYSTEM = """You find official public data sources for a lead-generation product. For the given US county \
(or independent city), find the official online sources for: building permits, code violations, property sales or \
deed transfers, delinquent tax lists, planning commission agendas, and government bid postings.

Only report sources on official government sites or their official vendors (Socrata, ArcGIS, Accela Citizen Access, \
Tyler EnerGov, CivicPlus, OpenGov, Citizenserve, iWorQ, Legistar). Prefer machine-readable endpoints (open-data APIs, \
CSV downloads, RSS feeds). Never report sources that require a login or that forbid automated access.

Finish with a single JSON object and nothing after it:
{"sources": [{"platform": "socrata|arcgis|accela|rss|html_list|agenda_pdf|csv|unknown", "kind": \
"permit|violation|sale|tax_delinquent|subdivision|bid", "title": "...", "url": "https://...", "note": "..."}]}"""


def claude_candidates(county_label: str) -> list[Candidate]:
    settings = get_settings()
    if not settings.ai_enabled:
        return []
    import anthropic

    from ..intel.ai import FALLBACK_BETA, _client

    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6}]
    messages: list = [{"role": "user", "content": f"County: {county_label}"}]
    response = None
    try:
        for _ in range(5):  # resume pause_turn up to 5 times
            response = _client().beta.messages.create(
                model=settings.ai_smart_model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks="default",
                system=RESEARCH_SYSTEM, messages=messages, tools=tools, output_config={"effort": "medium"})
            if response.stop_reason != "pause_turn":
                break
            # Resume: send the paused assistant turn back; the server continues where it stopped.
            messages = [*messages, {"role": "assistant", "content": response.content}]
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        log.warning("Claude source research failed: %s", exc)
        return []
    if response is None or response.stop_reason == "refusal":
        return []
    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{[\s\S]*\}\s*$", text.strip())
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []
    out = []
    for s in data.get("sources", []):
        url = str(s.get("url", ""))
        if not url.startswith("https://"):
            continue
        out.append(Candidate(platform=s.get("platform", "unknown"), kind=s.get("kind", "permit"),
                             title=str(s.get("title", ""))[:200], url=url, note=str(s.get("note", ""))[:300]))
    return out


def discover(fips: str, client: httpx.Client | None = None) -> list[Candidate]:
    from ..geodata import county, county_label

    c = county(fips)
    if c is None:
        return []
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True,
                                    headers={"User-Agent": get_settings().user_agent})
    try:
        found = socrata_candidates(c, client) + arcgis_candidates(c, client) + claude_candidates(county_label(fips))
    finally:
        if own:
            client.close()
    seen, unique = set(), []
    for cand in found:
        key = cand.url.split("?")[0].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    return unique
