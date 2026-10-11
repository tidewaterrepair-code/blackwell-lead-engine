"""Rule-based signal classifier.

Produces *tags* for a signal: building-work tags (tuned construction rules
below), trade tags (regex packs in data/tags.yaml) and real estate / storm tags
by signal kind. Rules are cheap and predictable; records they can't place can
go to the AI fallback (llm.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .taxonomy import trade_tag_defs

# Phrases removed before matching so they can't trigger a positive match
# (e.g. "garage door replacement" is not a garage build).
NOISE_PHRASES = [
    r"garage doors?", r"overhead doors?", r"bath ?fans?", r"exhaust fans?", r"kitchen hoods?",
    r"hood suppression", r"kitchen exhaust", r"deck coating", r"roof deck(ing)?",
    r"parking deck", r"deck (re)?sheathing", r"porch lights?",
]

# Permit types / work that are never our work on their own.
TRADE_ONLY = re.compile(
    r"\b(electrical|electric|plumbing|mechanical|hvac|heat pump|gas (line|piping)|fire (alarm|sprinkler|suppression)"
    r"|sprinkler|sign(age)?|elevator|amusement|tent|demolition|demo permit|re-?roof(ing)?|roofing|roof replacement"
    r"|solar|photovoltaic|pv system|generator|water heater|swimming pool|pool|fence|fencing|irrigation|backflow"
    r"|right of way|row permit|utility|sewer|septic|well|cell tower|antenna|land disturb(ance|ing)|grading"
    r"|zoning verification|certificate of occupancy|temporary)\b"
)

COMMERCIAL = re.compile(
    r"\b(commercial|retail|office|restaurant|warehouse|tenant|upfit|up-fit|fit-?out|church|school|hotel|motel"
    r"|medical|clinic|industrial|storage facility|bank|store|shopping|mall|apartments? complex|multi-?family)\b"
)

RESIDENTIAL_NOUN = r"(single[- ]family|sfd|sfr|sfh|dwelling|home|house|residence|residential|townho(?:me|use)s?|duplex|cottage)"

JOB_RULES: list[tuple[str, list[str]]] = [
    ("new_construction", [
        rf"\bnew\s+(?:\w+\s+){{0,3}}{RESIDENTIAL_NOUN}",
        rf"\bconstruct(?:ion of)?\s+(?:a\s+)?(?:new\s+)?(?:\w+\s+){{0,2}}{RESIDENTIAL_NOUN}",
        r"\bnew construction\b", r"\bnew build\b", r"\bsfd\b", r"\bnew sf[dr]?\b",
        r"\bsingle[- ]family (?:dwelling|detached|home|residence)\b.*\bnew\b",
        r"\b(?:subdivision|townhomes?|townhouses?|residential lots?|preliminary plat|final plat)\b",
    ]),
    ("addition", [
        r"\badditions?\b", r"\badd(?:ing)?\s+(?:a\s+)?(?:\w+\s+)?(?:room|bedroom|story|floor)\b",
        r"\b(?:second|2nd)\s+(?:story|floor)\b", r"\bsun ?rooms?\b", r"\bbump[- ]?outs?\b",
        r"\bin-?law suite\b", r"\bporch enclosure\b", r"\benclos(?:e|ed|ing)\s+(?:\w+\s+)?porch\b",
        r"\bfour[- ]season room\b", r"\bbonus room\b", r"\bfrog\b",
    ]),
    ("garage_framing", [
        r"\bgarages?\b", r"\bcarports?\b", r"\bdetached (?:accessory )?(?:structure|building|workshop)\b",
        r"\baccessory (?:structure|building|dwelling)\b", r"\bpole barn\b", r"\bworkshop\b",
    ]),
    ("deck", [
        r"\bdecks?\b", r"\bdecking\b", r"\bporch(?:es)?\b", r"\bpergolas?\b", r"\bgazebos?\b",
        r"\bscreen(?:ed)? (?:in )?(?:porch|room)\b", r"\bboardwalk\b", r"\bbalcon(?:y|ies)\b",
    ]),
    ("kitchen", [r"\bkitchens?\b"]),
    ("bath", [r"\bbath(?:room)?s?\b", r"\bshowers?\b", r"\bvanit(?:y|ies)\b", r"\btub\b"]),
    ("house_framing", [
        r"\bfram(?:e|ed|ing)\b", r"\bre-?fram", r"\bstructural (?:repair|framing|alteration|work)\b",
        r"\bjoists?\b", r"\brafters?\b", r"\btruss(?:es)?\b", r"\bload[- ]bearing\b", r"\bsister(?:ing)?\b",
    ]),
    ("remodel", [
        r"\bremodel(?:ing|ed)?\b", r"\brenovat(?:e|ion|ions|ing)\b", r"\balterations?\b",
        r"\binterior (?:alteration|renovation|remodel|work|finish)\b", r"\bconver(?:t|sion)\b",
        r"\bfinish(?:ed|ing)? (?:basement|attic|bonus)\b", r"\brepair(?:s)? (?:to|of) (?:dwelling|house|home)\b",
        r"\bfire damage\b", r"\bwater damage\b", r"\bdrywall\b", r"\brehab(?:ilitation)?\b",
    ]),
]

_COMPILED = [(job, [re.compile(p) for p in pats]) for job, pats in JOB_RULES]
_NOISE = re.compile("|".join(NOISE_PHRASES))
OWNERISH = re.compile(r"\b(owner|homeowner|self|home owner|n/?a|none|tbd|unknown)\b", re.I)


@dataclass
class Classification:
    job_type: str  # primary tag
    customer_type: str
    confidence: float
    relevant: bool
    commercial: bool
    matched: list[str]  # building-work tags
    tags: list[str] = field(default_factory=list)  # every tag (building + trade + kind)
    classified_by: str = "rules"


def _text(*parts: str | None) -> str:
    # ";" keeps patterns from matching across separate fields ("New" + "Residential").
    return " ; ".join(p for p in parts if p).lower()


def match_job_types(text: str) -> list[str]:
    text = _NOISE.sub(" ", text.lower())
    return [job for job, pats in _COMPILED if any(p.search(text) for p in pats)]


def is_contractor_listed(contractor: str | None) -> bool:
    if not contractor or not contractor.strip():
        return False
    return not OWNERISH.fullmatch(contractor.strip())


def classify(
    *,
    kind: str,
    title: str | None,
    description: str | None = None,
    permit_type: str | None = None,
    contractor_name: str | None = None,
    hints: list[str] | None = None,
) -> Classification:
    body = _text(title, description)
    meta = _text(permit_type, *(hints or []))
    full = f"{body} ; {meta}"

    matched = match_job_types(full)
    commercial = bool(COMMERCIAL.search(full))

    # A trade-only permit (electrical, roofing, ...) only counts when the free-text
    # work description itself names our kind of work. Permit adapters build the
    # title from the structured type fields, so the description is what decides.
    desc = body
    for piece in re.split(r"\s*/\s*", permit_type or "") + list(hints or []):
        if piece:
            desc = desc.replace(piece.lower(), " ")
    desc = desc.strip(" ·—-")
    trade_only = bool(TRADE_ONLY.search(meta)) or (bool(desc) and bool(TRADE_ONLY.search(desc))
                                                   and not match_job_types(desc))
    if trade_only:
        matched = match_job_types(desc)
    elif not matched and TRADE_ONLY.search(body):
        matched = []

    # "New" in the permit's work-type field plus a residential use is new construction
    # even when the description is terse (e.g. "SFD" or just a lot number).
    if (
        not trade_only
        and "new_construction" not in matched
        and re.search(r"\bnew\b", meta)
        and re.search(RESIDENTIAL_NOUN, full)
        and not {"addition", "deck", "garage_framing"} & set(matched)
    ):
        matched.insert(0, "new_construction")

    # Permit systems file decks and garages under a generic "Addition" work type;
    # the structure field is more specific unless the free text says addition.
    if "addition" in matched and {"deck", "garage_framing"} & set(matched) and "addition" not in desc:
        matched.remove("addition")

    trade_tags = match_trade_tags(full)
    extra = kind_tags(kind, full)
    tags = list(dict.fromkeys(matched + trade_tags + extra))
    # Kitchen/bath beat a generic "remodel" match; JOB_RULES order already handles that.
    job_type = matched[0] if matched else (trade_tags[0] if trade_tags else (extra[0] if extra else "other"))

    if kind in REALESTATE_KINDS:
        customer = "owner"
    elif kind == "storm":
        customer = "homeowner"
    elif kind == "bid":
        customer = "public"
    elif kind == "subdivision":
        customer = "builder"
    elif kind == "request":
        customer = "homeowner"
    elif job_type == "new_construction" or commercial or is_contractor_listed(contractor_name):
        customer = "builder"
    else:
        customer = "homeowner"

    if job_type == "other":
        confidence = 0.0
    else:
        hits = len(tags)
        confidence = min(0.95, 0.6 + 0.1 * hits + (0.1 if meta else 0))

    return Classification(
        job_type=job_type,
        customer_type=customer,
        confidence=round(confidence, 2),
        relevant=job_type != "other",
        commercial=commercial,
        matched=matched,
        tags=tags,
    )


REALESTATE_KINDS = {"sale", "violation", "tax_delinquent", "foreclosure", "probate", "eviction", "listing"}
KIND_TAGS = {
    "sale": "re_sale", "violation": "re_violation", "tax_delinquent": "re_tax_delinquent",
    "foreclosure": "re_foreclosure", "probate": "re_probate", "eviction": "re_eviction",
    "subdivision": "re_subdivision", "listing": "re_listing",
}
_STORM = [
    ("storm_hail", re.compile(r"\bhail")),
    ("storm_wind", re.compile(r"\b(wind|tornado|thunderstorm|derecho|hurricane|tropical storm|gust)")),
    ("storm_flood", re.compile(r"\b(flood|storm surge|flash flood|coastal flood)")),
]


def match_trade_tags(text: str) -> list[str]:
    text = text.lower()
    return [t.key for t in trade_tag_defs() if t.matches(text)]


def kind_tags(kind: str, text: str) -> list[str]:
    if kind == "storm":
        return [key for key, rx in _STORM if rx.search(text.lower())]
    tag = KIND_TAGS.get(kind)
    return [tag] if tag else []


CONSTRUCTIONISH = re.compile(
    r"\b(build|construct|renovat|repair|install|structure|carpent|framer|contractor|project|room|wall|floor)\w*"
)


def worth_llm_review(text: str) -> bool:
    """Only send unclassified records that at least look like building work."""
    return bool(CONSTRUCTIONISH.search(text.lower())) and not TRADE_ONLY.search(text.lower())
