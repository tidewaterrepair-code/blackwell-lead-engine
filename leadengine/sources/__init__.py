"""Source adapter registry: sources.yaml `type:` -> adapter class."""

from __future__ import annotations

import httpx

from .accela import AccelaAdapter
from .agendas import AgendaPDFAdapter
from .arcgis import ArcGISAdapter
from .base import Adapter, LeadInput, RawItem
from .feeds import HTMLListAdapter, RSSAdapter
from .inbox import IMAPAdapter
from .socrata import SocrataAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    "socrata": SocrataAdapter,
    "arcgis": ArcGISAdapter,
    "accela": AccelaAdapter,
    "rss": RSSAdapter,
    "html_list": HTMLListAdapter,
    "agenda_pdf": AgendaPDFAdapter,
    "imap": IMAPAdapter,
}


def build_adapter(source_id: str, config: dict, client: httpx.Client | None = None) -> Adapter:
    try:
        cls = ADAPTERS[config["type"]]
    except KeyError as exc:
        raise ValueError(f"source {source_id!r}: unknown type {config.get('type')!r}") from exc
    return cls(source_id, config, client=client)


__all__ = ["ADAPTERS", "Adapter", "LeadInput", "RawItem", "build_adapter"]
