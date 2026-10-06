"""Optional free local-LLM fallback via Ollama (https://ollama.com).

Only used when OLLAMA_URL is set (e.g. http://ollama:11434) and the rules
returned "other" for something that still looks like building work.
"""

from __future__ import annotations

import json
import logging

import httpx

from .classify import Classification
from .config import get_settings
from .db import JOB_TYPES

log = logging.getLogger(__name__)

PROMPT = """You label construction leads for a residential carpentry/framing contractor.
Pick the single best job_type from: {job_types}.
Use "other" if the work is not one of these (e.g. electrical only, roofing, HVAC, fences, pools, signs).
Answer with JSON only: {{"job_type": "...", "confidence": 0.0-1.0}}

Lead text:
{text}
"""


def llm_classify(text: str, base: Classification) -> Classification | None:
    settings = get_settings()
    if not settings.ollama_url:
        return None
    try:
        resp = httpx.post(
            f"{settings.ollama_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": PROMPT.format(job_types=", ".join(JOB_TYPES), text=text[:2000]),
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = json.loads(resp.json().get("response") or "{}")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("ollama classification failed: %s", exc)
        return None
    job_type = data.get("job_type")
    if job_type not in JOB_TYPES or job_type == "other":
        return None
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return Classification(
        job_type=job_type,
        customer_type=base.customer_type,
        confidence=round(min(confidence, 0.8), 2),
        relevant=True,
        commercial=base.commercial,
        matched=[job_type],
        classified_by="llm",
    )
