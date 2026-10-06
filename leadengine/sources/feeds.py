"""Bid boards and other list-style pages: RSS/Atom feeds and plain HTML lists.

sources.yaml (RSS, e.g. a CivicPlus "Bid Postings" feed):
    norfolk-bids:
      type: rss
      kind: bid
      url: https://www.norfolk.gov/RSSFeed.aspx?ModID=76&CID=All-bids.xml
      city: Norfolk

sources.yaml (HTML list, any page with repeated items):
    some-bids:
      type: html_list
      kind: bid
      url: https://example.gov/bids
      item: "table.bids tr"        # CSS selector for each listing
      title: "td:nth-child(2)"     # selector inside the item (text)
      link: "a"                    # selector inside the item (href); defaults to first link
      date: "td:nth-child(3)"      # optional posted date
      due: "td:nth-child(4)"       # optional due/closing date
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from .base import (
    Adapter,
    LeadInput,
    RawItem,
    clean,
    find_city,
    find_due_date,
    find_email,
    find_phone,
    parse_date,
)


def html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    return clean(BeautifulSoup(html, "html.parser").get_text(" "))


def text_lead(adapter: Adapter, payload: dict) -> LeadInput | None:
    """Normalize a {title, link, summary, published, due} payload into a lead."""
    title = clean(payload.get("title"))
    if not title:
        return None
    summary = html_to_text(payload.get("summary"))
    blob = f"{title} {summary or ''}"
    return LeadInput(
        external_id=payload["id"],
        kind=adapter.kind,
        title=title[:480],
        description=summary,
        city=adapter.default_city or find_city(blob),
        url=payload.get("link"),
        posted_at=parse_date(payload.get("published")),
        due_at=parse_date(payload.get("due")) or find_due_date(blob),
        phone=find_phone(summary),
        email=find_email(summary),
        hints=list(adapter.config.get("hints", [])),
    )


def _item_id(*parts: str | None) -> str:
    joined = "|".join(p or "" for p in parts)
    return joined if len(joined) <= 280 else hashlib.sha1(joined.encode()).hexdigest()


class RSSAdapter(Adapter):
    kind = "bid"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        resp = self.client.get(self.config["url"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            published = entry.get("published") or entry.get("updated")
            payload = {
                "id": _item_id(entry.get("id") or entry.get("link") or entry.get("title")),
                "title": entry.get("title"),
                "link": entry.get("link"),
                "summary": entry.get("summary") or entry.get("description"),
                "published": published,
            }
            posted = parse_date(published)
            if posted and posted < since and not self.config.get("ignore_dates"):
                continue
            yield RawItem(external_id=payload["id"], payload=payload)

    def normalize(self, payload: dict) -> LeadInput | None:
        return text_lead(self, payload)


class HTMLListAdapter(Adapter):
    kind = "bid"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        url = self.config["url"]
        resp = self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select(self.config["item"]):
            title_el = item.select_one(self.config["title"]) if self.config.get("title") else item
            link_el = item.select_one(self.config.get("link", "a[href]"))
            title = clean(title_el.get_text(" ")) if title_el else None
            if not title:
                continue
            link = urljoin(url, link_el["href"]) if link_el and link_el.get("href") else None
            payload = {
                "id": _item_id(link or title),
                "title": title,
                "link": link,
                "summary": str(item),
                "published": self._text(item, "date"),
                "due": self._text(item, "due"),
            }
            yield RawItem(external_id=payload["id"], payload=payload)

    def _text(self, item, key: str) -> str | None:
        sel = self.config.get(key)
        el = item.select_one(sel) if sel else None
        return clean(el.get_text(" ")) if el else None

    def normalize(self, payload: dict) -> LeadInput | None:
        return text_lead(self, payload)
