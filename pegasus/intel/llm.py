"""Fallback labeling for records the rules couldn't place: Claude first, then a local Ollama model."""

from __future__ import annotations

import json
import logging

import httpx

from ..config import get_settings
from .classify import Classification
from .taxonomy import tags as all_tags

log = logging.getLogger(__name__)

OLLAMA_PROMPT = """You label construction leads. Pick every job tag that applies from: {tags}.
Use an empty list if the work is none of these. Answer with JSON only: {{"tags": [...], "confidence": 0.0-1.0}}

Record:
{text}
"""


def _allowed() -> list[str]:
    return [k for k, t in all_tags().items() if t.group in ("building", "trade")]


def _ollama(text: str) -> tuple[list[str], float] | None:
    settings = get_settings()
    if not settings.ollama_url:
        return None
    try:
        resp = httpx.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json={
            "model": settings.ollama_model, "format": "json", "stream": False, "options": {"temperature": 0},
            "prompt": OLLAMA_PROMPT.format(tags=", ".join(_allowed()), text=text[:2000]),
        }, timeout=120)
        resp.raise_for_status()
        data = json.loads(resp.json().get("response") or "{}")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("ollama classification failed: %s", exc)
        return None
    tags = [t for t in data.get("tags", []) if t in _allowed()]
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return tags, min(confidence, 0.75)


def llm_classify(text: str, base: Classification) -> Classification | None:
    from .ai import label_tags

    result = label_tags(text, _allowed()) or _ollama(text)
    if not result or not result[0]:
        return None
    tags, confidence = result
    return Classification(
        job_type=tags[0], customer_type=base.customer_type, confidence=round(confidence, 2), relevant=True,
        commercial=base.commercial, matched=[t for t in tags if all_tags()[t].group == "building"], tags=tags,
        classified_by="ai",
    )
