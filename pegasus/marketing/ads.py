"""campaigns.yaml -> Meta bulk-import CSV, Google Ads Editor CSV and a UTM link sheet.

Column names follow the Meta Ads Manager bulk template and the Google Ads Editor
import format. Both vendors update their templates; if an import complains, download
a fresh template from the platform and map columns (the data here is complete).
"""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlencode

import yaml

GOOGLE_HEADLINE_MAX = 30
GOOGLE_DESCRIPTION_MAX = 90
GOOGLE_PATH_MAX = 15
META_HEADLINE_MAX = 40
META_PRIMARY_MAX = 300


class AdSpecError(ValueError):
    pass


def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def utm_link(base: str, source: str, medium: str, campaign: str, content: str) -> str:
    return f"{base}/?{urlencode({'utm_source': source, 'utm_medium': medium, 'utm_campaign': slug(campaign), 'utm_content': slug(content)})}"


def validate(spec: dict) -> list[str]:
    """Return a list of problems (empty = valid). Checks platform character limits."""
    problems = []
    for camp in spec.get("google", []):
        for ag in camp["ad_groups"]:
            if not 3 <= len(ag["headlines"]) <= 15:
                problems.append(f"{ag['name']}: responsive search ads need 3-15 headlines")
            if not 2 <= len(ag["descriptions"]) <= 4:
                problems.append(f"{ag['name']}: responsive search ads need 2-4 descriptions")
            for h in ag["headlines"]:
                if len(h) > GOOGLE_HEADLINE_MAX:
                    problems.append(f"{ag['name']}: headline over {GOOGLE_HEADLINE_MAX} chars: {h!r}")
            for d in ag["descriptions"]:
                if len(d) > GOOGLE_DESCRIPTION_MAX:
                    problems.append(f"{ag['name']}: description over {GOOGLE_DESCRIPTION_MAX} chars: {d!r}")
            for p in ag.get("path", []):
                if len(p) > GOOGLE_PATH_MAX:
                    problems.append(f"{ag['name']}: path over {GOOGLE_PATH_MAX} chars: {p!r}")
    for camp in spec.get("meta", []):
        for aset in camp["ad_sets"]:
            for ad in aset["ads"]:
                if len(ad["headline"]) > META_HEADLINE_MAX:
                    problems.append(f"{ad['name']}: Meta headline over {META_HEADLINE_MAX} chars")
                if len(ad["primary"]) > META_PRIMARY_MAX:
                    problems.append(f"{ad['name']}: primary text over {META_PRIMARY_MAX} chars")
                if not (ad.get("video") or ad.get("image")):
                    problems.append(f"{ad['name']}: needs a video or image")
    return problems


def export(spec_path: Path, out_dir: Path) -> dict[str, Path]:
    spec = yaml.safe_load(spec_path.read_text())
    problems = validate(spec)
    if problems:
        raise AdSpecError("\n".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)
    base, geo = spec["landing"].rstrip("/"), spec["geo"]
    links: list[list[str]] = []

    meta_path = out_dir / "meta_bulk.csv"
    with meta_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Campaign Name", "Campaign Status", "Campaign Objective", "Buying Type", "Ad Set Name",
                    "Ad Set Run Status", "Ad Set Daily Budget", "Location", "Location Radius (mi)", "Age Min",
                    "Age Max", "Flexible Inclusions (interests)", "Custom Audiences", "Optimization Goal",
                    "Ad Name", "Ad Status", "Title", "Body", "Link", "Call to Action", "Creative Asset"])
        for camp in spec.get("meta", []):
            per_set = round(camp["daily_budget"] / max(1, len(camp["ad_sets"])), 2)
            for aset in camp["ad_sets"]:
                for ad in aset["ads"]:
                    link = utm_link(base, "meta", "paid_social", camp["campaign"], ad["name"])
                    links.append(["meta", camp["campaign"], ad["name"], link])
                    w.writerow([camp["campaign"], "PAUSED", camp["objective"], "AUCTION", aset["name"], "ACTIVE",
                                per_set, f"{geo['city']}, {geo['region']}, {geo['country']}", geo["radius_miles"],
                                aset["age"][0], aset["age"][1], "; ".join(aset.get("interests", [])),
                                aset.get("custom_audience", ""), "LEAD_GENERATION" if "LEADS" in camp["objective"]
                                else "OFFSITE_CONVERSIONS", ad["name"], "ACTIVE", ad["headline"], ad["primary"],
                                link, ad.get("cta", "SIGN_UP"), ad.get("video") or ad.get("image")])

    google_path = out_dir / "google_ads_editor.csv"
    with google_path.open("w", newline="") as f:
        w = csv.writer(f)
        header = (["Campaign", "Campaign Type", "Campaign Status", "Budget", "Bid Strategy Type", "Location",
                   "Ad Group", "Ad Group Status", "Keyword", "Criterion Type", "Ad Type", "Final URL", "Path 1", "Path 2"]
                  + [f"Headline {i}" for i in range(1, 16)] + [f"Description {i}" for i in range(1, 5)])
        w.writerow(header)
        blank = [""] * (len(header))

        def row(**cols):
            r = list(blank)
            for k, v in cols.items():
                r[header.index(k)] = v
            return r

        for camp in spec.get("google", []):
            w.writerow(row(**{"Campaign": camp["campaign"], "Campaign Type": "Search", "Campaign Status": "Paused",
                              "Budget": camp["daily_budget"], "Bid Strategy Type": camp["bid_strategy"],
                              "Location": f"{geo['city']}, {geo['region']} (+{geo['radius_miles']} mi)"}))
            for neg in camp.get("negatives", []):
                w.writerow(row(**{"Campaign": camp["campaign"], "Keyword": neg, "Criterion Type": "Campaign Negative Phrase"}))
            for ag in camp["ad_groups"]:
                w.writerow(row(**{"Campaign": camp["campaign"], "Ad Group": ag["name"], "Ad Group Status": "Enabled"}))
                for kw in ag["keywords"]:
                    for match in ("Phrase", "Exact"):
                        w.writerow(row(**{"Campaign": camp["campaign"], "Ad Group": ag["name"], "Keyword": kw,
                                          "Criterion Type": match}))
                link = utm_link(base, "google", "cpc", camp["campaign"], ag["name"])
                links.append(["google", camp["campaign"], ag["name"], link])
                ad = {"Campaign": camp["campaign"], "Ad Group": ag["name"], "Ad Type": "Responsive search ad",
                      "Final URL": link, "Path 1": (ag.get("path") or ["", ""])[0], "Path 2": (ag.get("path") or ["", ""])[1]}
                ad.update({f"Headline {i + 1}": h for i, h in enumerate(ag["headlines"])})
                ad.update({f"Description {i + 1}": d for i, d in enumerate(ag["descriptions"])})
                w.writerow(row(**ad))

    utm_path = out_dir / "utm_links.csv"
    with utm_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["platform", "campaign", "ad / ad group", "url"])
        w.writerows(links)
    return {"meta": meta_path, "google": google_path, "utm": utm_path}
