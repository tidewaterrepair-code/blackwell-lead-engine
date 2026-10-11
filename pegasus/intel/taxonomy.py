"""Loads the trade/tag/timeline data files in pegasus/intel/data/."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).parent / "data"


@dataclass(frozen=True)
class TagDef:
    key: str
    label: str
    group: str
    patterns: tuple[re.Pattern, ...] = ()
    unless: tuple[re.Pattern, ...] = ()

    def matches(self, text: str) -> bool:
        if not self.patterns or not any(p.search(text) for p in self.patterns):
            return False
        return not any(u.search(text) for u in self.unless)


@dataclass(frozen=True)
class TradeDef:
    key: str
    label: str
    group: str
    icon: str
    ticket: int
    tags: frozenset[str]
    kinds: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class NextJob:
    trade: str
    tag: str
    start_day: int
    end_day: int
    probability: float
    reason: str


@dataclass(frozen=True)
class TimelineRule:
    name: str
    when: frozenset[str]
    kinds: frozenset[str]
    next: tuple[NextJob, ...]


def _load(name: str) -> dict:
    return yaml.safe_load((DATA / name).read_text())


@lru_cache(maxsize=1)
def tags() -> dict[str, TagDef]:
    out: dict[str, TagDef] = {}
    for group, items in _load("tags.yaml").items():
        for key, spec in items.items():
            spec = spec or {}
            out[key] = TagDef(
                key=key,
                label=spec.get("label", key),
                group=group,
                patterns=tuple(re.compile(p, re.I) for p in spec.get("patterns", [])),
                unless=tuple(re.compile(p, re.I) for p in spec.get("unless", [])),
            )
    return out


@lru_cache(maxsize=1)
def trades() -> dict[str, TradeDef]:
    known = tags()
    out: dict[str, TradeDef] = {}
    for key, spec in _load("trades.yaml")["trades"].items():
        unknown = set(spec["tags"]) - set(known)
        if unknown:
            raise ValueError(f"trade {key} references unknown tags {sorted(unknown)}")
        out[key] = TradeDef(
            key=key,
            label=spec["label"],
            group=spec.get("group", "trades"),
            icon=spec.get("icon", "hammer"),
            ticket=int(spec.get("ticket", 10000)),
            tags=frozenset(spec["tags"]),
            kinds=frozenset(spec.get("kinds", [])),
        )
    return out


@lru_cache(maxsize=1)
def timeline_rules() -> tuple[TimelineRule, ...]:
    known_trades, known_tags = trades(), tags()
    rules = []
    for spec in _load("timelines.yaml")["rules"]:
        nexts = []
        for trade, tag, start, end, prob, reason in spec["next"]:
            if trade not in known_trades or tag not in known_tags:
                raise ValueError(f"timeline {spec['name']}: unknown trade/tag {trade}/{tag}")
            nexts.append(NextJob(trade, tag, int(start), int(end), float(prob), reason))
        rules.append(TimelineRule(
            name=spec["name"],
            when=frozenset(spec["when"]),
            kinds=frozenset(spec.get("kinds", [])),
            next=tuple(nexts),
        ))
    return tuple(rules)


def trade_tag_defs() -> list[TagDef]:
    return [t for t in tags().values() if t.group == "trade"]


def tag_label(key: str) -> str:
    tag = tags().get(key)
    return tag.label if tag else key.replace("_", " ").title()


def tags_for_trades(trade_keys) -> set[str]:
    all_trades = trades()
    out: set[str] = set()
    for key in trade_keys or []:
        if key in all_trades:
            out |= all_trades[key].tags
    return out


def kinds_for_trades(trade_keys) -> set[str]:
    all_trades = trades()
    out: set[str] = set()
    for key in trade_keys or []:
        if key in all_trades:
            out |= all_trades[key].kinds
    return out


def matching_trades(signal_tags, signal_kind: str, trade_keys) -> list[str]:
    """Which of the given trades this signal is a lead for (in the given order)."""
    all_trades = trades()
    tagset = set(signal_tags or [])
    hits = []
    for key in trade_keys or []:
        trade = all_trades.get(key)
        if trade and (trade.tags & tagset or signal_kind in trade.kinds):
            hits.append(key)
    return hits
