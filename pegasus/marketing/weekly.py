"""Weekly data-driven posts ("This week in Virginia Beach: 47 new projects") from live Pegasus data.

Output per city: a markdown post (caption + carousel slides) and a banner spec that the
renderer turns into images. Optional: Claude rewrites the caption in the brand voice.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from ..config import get_settings
from ..db import session_scope, utcnow
from ..intel.taxonomy import tag_label
from ..models import Signal
from ..web.site import money, slugify

PUBLIC_KINDS = ("permit", "bid", "subdivision", "storm")


def city_stats(city: str, state: str, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)
    with session_scope() as s:
        rows = s.scalars(select(Signal).where(
            func.lower(Signal.city) == city.lower(), Signal.state == state.upper(), Signal.created_at >= since,
            Signal.duplicate_of_id.is_(None), Signal.kind.in_(PUBLIC_KINDS),
            ~Signal.source_id.like("manual:%"), ~Signal.source_id.like("mls:%"))).all()
        tags = Counter(t for r in rows for t in (r.tags or []))
        streets = Counter(" ".join((r.address or "").split(",")[0].split()[1:]).title() for r in rows if r.address)
        return {
            "city": city, "state": state.upper(), "days": days, "count": len(rows),
            "value": sum(r.est_value or 0 for r in rows),
            "top_tags": [(tag_label(t), n) for t, n in tags.most_common(6)],
            "top_streets": [(st, n) for st, n in streets.most_common(5) if st],
            "biggest": [{"job": tag_label(r.primary_tag), "value": r.est_value,
                         "street": " ".join((r.address or "").split(",")[0].split()[1:]).title()}
                        for r in sorted(rows, key=lambda r: -(r.est_value or 0))[:3] if r.est_value],
        }


def compose(stats: dict) -> dict:
    city, n = stats["city"], stats["count"]
    base = get_settings().public_url
    url = f"{base}/leads/{stats['state'].lower()}/{slugify(city)}"
    lines = [f"{label}: {count}" for label, count in stats["top_tags"]]
    caption = (f"This week in {city}: {n} new projects filed, worth about {money(stats['value'])}.\n\n"
               + "\n".join(f"• {l}" for l in lines[:5])
               + f"\n\nEvery one is a lead for someone. Pegasus ranks them for your trade every morning. Full list: {url}")
    slides = [f"This week in {city}: {n} new projects", *[f"{label}: {count}" for label, count in stats["top_tags"][:4]],
              f"Get them with addresses every morning → {base.split('://', 1)[-1]}"]
    banner = {"id": f"weekly-{slugify(city)}", "kicker": f"This week in {city}",
              "headline": f"{n} new projects. {money(stats['value'])} in work.",
              "sub": " · ".join(f"{label} {count}" for label, count in stats["top_tags"][:3]),
              "cta": "See them first", "stat": {"value": str(n), "label": "projects"}}
    return {"caption": caption, "slides": slides, "banner": banner, "url": url}


def ai_polish(caption: str) -> str:
    from ..intel.ai import ask_json

    data = ask_json(
        "You edit social captions for Pegasus, a lead-intelligence app for contractors and agents. Keep every "
        "number and URL exactly as given. Plain, confident, no hype, no emojis beyond one, under 600 characters.",
        caption, {"type": "object", "properties": {"caption": {"type": "string"}}, "required": ["caption"],
                  "additionalProperties": False}, effort="low", max_tokens=800)
    return (data or {}).get("caption") or caption


def write_weekly(cities: list[tuple[str, str]], out_dir: Path, polish: bool = False) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for city, state in cities:
        stats = city_stats(city, state)
        if not stats["count"]:
            continue
        post = compose(stats)
        if polish:
            post["caption"] = ai_polish(post["caption"])
        md = out_dir / f"{slugify(city)}.md"
        md.write_text(f"# This week in {city}\n\n## Caption\n\n{post['caption']}\n\n## Carousel slides\n\n"
                      + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(post["slides"])) + "\n")
        (out_dir / f"{slugify(city)}.json").write_text(json.dumps({"stats": stats, **post}, indent=2, default=str))
        written.append(md)
    return written
