"""Claude-powered intelligence: labels for odd records, lead briefs, outreach scripts.

Everything here is optional. Claude is reached one of two ways:
- ANTHROPIC_API_KEY: the Messages API, billed per token.
- CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`): headless Claude Code (`claude -p`)
  on a Claude subscription. Used only when there is no API key.
With neither, Pegasus falls back to a local Ollama model (OLLAMA_URL) or to deterministic
templates, so the product works without AI spend. Models are set with AI_FAST_MODEL / AI_SMART_MODEL.

Requests opt into server-side refusal fallbacks (`fallbacks: "default"`), so a
safety-classifier decline is retried on Anthropic's recommended model instead
of failing.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from functools import lru_cache

from ..config import get_settings

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@lru_cache(maxsize=1)
def _client():
    import anthropic

    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=3, timeout=120)


def run_claude_cli(system: str, prompt: str, *, model: str, effort: str = "low", schema: dict | None = None,
                   tools: str = "", max_turns: int = 3, timeout: int = 180) -> dict | None:
    """One headless Claude Code run (`claude -p`). Returns its JSON result envelope, or None on any failure.

    Runs isolated from any local Claude Code setup: no settings files, MCP servers, slash commands
    or saved sessions, and only the built-in tools named in `tools` ("" = none).
    """
    exe = shutil.which("claude")
    if not exe:
        log.warning("CLAUDE_CODE_OAUTH_TOKEN is set but the claude CLI is not installed; skipping AI step")
        return None
    cmd = [exe, "-p", "--output-format", "json", "--no-session-persistence", "--strict-mcp-config",
           "--setting-sources", "", "--disable-slash-commands", "--model", model, "--effort", effort,
           "--max-turns", str(max_turns), "--system-prompt", system, "--tools", tools]
    if tools:
        cmd += ["--allowedTools", tools]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": get_settings().claude_code_oauth_token or ""}
    env.pop("ANTHROPIC_API_KEY", None)  # never let a stray key switch billing to the API
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("claude CLI failed to run: %s", exc)
        return None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        log.warning("claude CLI exit %s with non-JSON output: %s", proc.returncode, (proc.stderr or proc.stdout)[:300])
        return None
    if data.get("is_error") or data.get("subtype") != "success":
        log.warning("claude CLI run failed: %s", str(data.get("result") or data.get("subtype"))[:300])
        return None
    return data


def _ask_json_cli(system: str, user: str, schema: dict, model: str, effort: str) -> dict | None:
    data = run_claude_cli(system, user, model=model, effort=effort, schema=schema)
    if data is None:
        return None
    out = data.get("structured_output")
    if isinstance(out, dict):
        return out
    try:
        return json.loads(data.get("result") or "")
    except ValueError:
        log.warning("claude CLI returned non-JSON output")
        return None


def ask_json(system: str, user: str, schema: dict, *, model: str | None = None, effort: str = "low",
             max_tokens: int = 2000) -> dict | None:
    """One Claude call with a JSON-schema-constrained answer. Returns None on any failure."""
    settings = get_settings()
    if not settings.ai_enabled:
        return None
    if settings.ai_backend == "cli":
        return _ask_json_cli(system, user, schema, model or settings.ai_fast_model, effort)
    import anthropic

    try:
        response = _client().beta.messages.create(
            model=model or settings.ai_fast_model,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.RateLimitError:
        log.warning("Claude rate limited; skipping AI step")
        return None
    except anthropic.APIStatusError as exc:
        log.warning("Claude API error %s: %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("Claude unreachable; skipping AI step")
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        log.info("Claude stop_reason=%s; skipping", response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except ValueError:
        log.warning("Claude returned non-JSON output")
        return None


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or list(properties),
            "additionalProperties": False}


# ---------------------------------------------------------------- labeling

LABEL_SYSTEM = """You label public records (building permits, bids, homeowner requests) for a lead-generation \
product used by contractors in every trade. Choose every job tag that clearly applies from the allowed list. \
Use an empty list when the record is not construction or home-improvement work. Never invent tags."""


def label_tags(text: str, allowed: list[str]) -> tuple[list[str], float] | None:
    schema = _schema({
        "tags": {"type": "array", "items": {"type": "string", "enum": allowed}},
        "confidence": {"type": "number"},
    })
    data = ask_json(LABEL_SYSTEM, f"Allowed tags: {', '.join(allowed)}\n\nRecord:\n{text[:3000]}", schema,
                    max_tokens=500)
    if not data:
        return None
    tags = [t for t in data.get("tags", []) if t in allowed]
    try:
        confidence = max(0.0, min(0.85, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return tags, confidence


# ---------------------------------------------------------------- lead briefs

BRIEF_SYSTEM = """You write short, factual lead briefs for a contractor or real estate agent deciding whether \
to pursue a lead. Use only the facts provided; if something is unknown, don't guess. Keep the tone practical \
and plain, no hype.

Compliance rules for any outreach you draft:
- Never mention or infer anything about the owner's personal characteristics (age, health, race, religion, \
national origin, sex, disability, family status) or their finances beyond what is in public record facts given.
- Don't reference distress (foreclosure, tax debt, probate, eviction) directly in the opening of outreach; \
lead with a neutral, helpful offer.
- Phone/text scripts must assume the person has NOT consented to marketing; offer to stop contact on request."""


def lead_brief(facts: dict, audience: str) -> dict | None:
    """AI brief: summary, why now, opener script and talking points."""
    schema = _schema({
        "summary": {"type": "string"},
        "why_now": {"type": "string"},
        "opener": {"type": "string"},
        "talking_points": {"type": "array", "items": {"type": "string"}},
    })
    user = (f"Audience: {audience}\n\nLead facts (JSON):\n{json.dumps(facts, default=str, sort_keys=True)}\n\n"
            "Write: summary (2 sentences), why_now (1 sentence on timing), opener (a 2-3 sentence first "
            "message), talking_points (3 short bullets).")
    return ask_json(BRIEF_SYSTEM, user, schema, model=get_settings().ai_smart_model, effort="medium",
                    max_tokens=3000)


def template_brief(facts: dict, audience: str) -> dict:
    """Deterministic brief used when AI is off or unavailable."""
    what = facts.get("job") or facts.get("kind") or "project"
    where = facts.get("address") or facts.get("city") or "your area"
    reasons = facts.get("reasons") or []
    summary = f"{facts.get('title') or what} at {where}."
    if facts.get("value"):
        summary += f" Reported value about ${facts['value']:,.0f}."
    why = facts.get("prediction") or (", ".join(reasons) if reasons else "Recently filed public record.")
    if audience == "realestate":
        opener = (f"Hi, this is {{your_name}} with {{company}}. I work with homeowners around {where} and wanted to "
                  "see if you'd be open to a no-pressure conversation about your property's value and options. "
                  "If now isn't a good time, just let me know and I won't reach out again.")
    else:
        opener = (f"Hi, this is {{your_name}} with {{company}}. I saw the {what.lower()} project at {where} and we "
                  "do this kind of work locally. Would it help to get a second quote or a hand with any part of "
                  "it? If not, no problem, I won't follow up.")
    return {"summary": summary, "why_now": why, "opener": opener,
            "talking_points": [f"Local {what.lower()} experience", "Licensed and insured",
                               "Fast, written estimate"]}
