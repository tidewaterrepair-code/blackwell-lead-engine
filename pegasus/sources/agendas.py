"""New-subdivision watcher: scans planning commission / council agenda PDFs.

Pulls agenda links from an index page or RSS feed, downloads PDFs it hasn't
seen yet, and turns each agenda item that mentions residential development
(subdivisions, rezonings for homes, plats, townhomes...) into a lead.

sources.yaml:
    vb-planning-agendas:
      type: agenda_pdf
      kind: subdivision
      index: https://example.gov/AgendaCenter          # HTML page or RSS feed
      link_pattern: "(?i)agenda.*(\\.pdf|ViewFile)"     # which links are agendas
      city: Virginia Beach
      max_docs: 5
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from .base import Adapter, LeadInput, RawItem, clean, find_city

log = logging.getLogger(__name__)

DEVELOPMENT = re.compile(
    r"\b(subdivi(?:sion|de)|re-?zon(?:e|ing)|preliminary plat|final plat|plat\b|townho(?:me|use)s?"
    r"|single[- ]family|residential lots?|dwelling units?|lots? for|planned unit development|\bpud\b"
    r"|cluster development|duplex(?:es)?|age[- ]restricted|residential development)",
    re.IGNORECASE,
)
ITEM_START = re.compile(r"(?m)^\s*(?:item\s+)?(?:\d{1,2}|[A-Z])[.)]\s+(?=\S)")


def split_items(text: str) -> list[str]:
    """Split agenda text into numbered items; fall back to paragraphs."""
    starts = [m.start() for m in ITEM_START.finditer(text)]
    if len(starts) >= 2:
        bounds = starts + [len(text)]
        items = [text[a:b] for a, b in zip(bounds, bounds[1:])]
    else:
        items = re.split(r"\n\s*\n", text)
    return [clean(i) for i in items if clean(i)]


def development_items(text: str) -> list[str]:
    return [item for item in split_items(text) if DEVELOPMENT.search(item) and len(item) > 40]


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class AgendaPDFAdapter(Adapter):
    kind = "subdivision"

    def agenda_links(self) -> list[tuple[str, str | None]]:
        index = self.config["index"]
        resp = self.client.get(index)
        resp.raise_for_status()
        pattern = re.compile(self.config.get("link_pattern", r"(?i)agenda"))
        links: list[tuple[str, str | None]] = []
        ctype = resp.headers.get("content-type", "")
        if "xml" in ctype or "rss" in ctype or resp.text.lstrip().startswith("<?xml"):
            for entry in feedparser.parse(resp.content).entries:
                link = entry.get("link")
                if link and (pattern.search(link) or pattern.search(entry.get("title", ""))):
                    links.append((link, entry.get("published")))
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(index, a["href"])
                if pattern.search(href) or pattern.search(a.get_text(" ")):
                    links.append((href, None))
        seen, unique = set(), []
        for link, published in links:
            if link not in seen:
                seen.add(link)
                unique.append((link, published))
        return unique[: int(self.config.get("max_docs", 5))]

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        for link, published in self.agenda_links():
            if self.known(link):
                continue
            resp = self.client.get(link)
            resp.raise_for_status()
            if resp.content[:4] == b"%PDF":
                text = pdf_text(resp.content)
            else:
                text = BeautifulSoup(resp.text, "html.parser").get_text("\n")
            for item in development_items(text):
                digest = hashlib.sha1(item[:300].encode()).hexdigest()[:12]
                yield RawItem(
                    external_id=f"{link}#{digest}",
                    payload={"text": item, "link": link, "published": published},
                )
            # Marker so the document isn't downloaded again next run.
            yield RawItem(external_id=link, payload={"_doc": True, "link": link})

    def normalize(self, payload: dict) -> LeadInput | None:
        if payload.get("_doc"):
            return None
        text = payload["text"]
        first = re.split(r"(?<=[.;])\s", text, maxsplit=1)[0]
        from .base import parse_date

        return LeadInput(
            external_id=f"{payload['link']}#{hashlib.sha1(text[:300].encode()).hexdigest()[:12]}",
            kind=self.kind,
            title=f"Agenda: {first[:200]}",
            description=text[:4000],
            city=self.default_city or find_city(text),
            url=payload["link"],
            posted_at=parse_date(payload.get("published")),
            hints=["new residential development"],
        )
