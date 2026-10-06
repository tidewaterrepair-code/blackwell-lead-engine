"""Runtime settings (environment variables) and the sources.yaml loader."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_float(name: str) -> float | None:
    value = _env(name)
    return float(value) if value is not None else None


@dataclass
class Settings:
    data_dir: Path
    database_url: str
    sources_file: Path
    secret_key: str
    app_password: str | None
    public_url: str
    # Your shop / home base, used for distance scoring.
    base_lat: float | None
    base_lng: float | None
    # Scheduling (cron-style hour lists, server local time).
    ingest_hours: str
    digest_hour: int
    lookback_days: int
    # Notifications (all optional, all free).
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    digest_to: str | None
    digest_from: str | None
    digest_min_score: int
    ntfy_url: str | None
    hot_lead_score: int
    # Optional local LLM via Ollama for records the rules can't classify.
    ollama_url: str | None
    ollama_model: str
    # Geocoding (US Census geocoder, free, no key).
    geocode_enabled: bool
    geocode_per_run: int
    user_agent: str = field(default="BlackwellLeadEngine/0.1 (+self-hosted)")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(_env("LEADENGINE_DATA_DIR", "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=data_dir,
        database_url=_env("DATABASE_URL", f"sqlite:///{data_dir / 'leads.db'}"),
        sources_file=Path(_env("SOURCES_FILE", "sources.yaml")).resolve(),
        secret_key=_env("SECRET_KEY", "dev-insecure-change-me"),
        app_password=_env("APP_PASSWORD"),
        public_url=_env("PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        base_lat=_env_float("BASE_LAT"),
        base_lng=_env_float("BASE_LNG"),
        ingest_hours=_env("INGEST_HOURS", "6,14"),
        digest_hour=int(_env("DIGEST_HOUR", "7")),
        lookback_days=int(_env("LOOKBACK_DAYS", "30")),
        smtp_host=_env("SMTP_HOST"),
        smtp_port=int(_env("SMTP_PORT", "587")),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        digest_to=_env("DIGEST_TO"),
        digest_from=_env("DIGEST_FROM") or _env("SMTP_USER"),
        digest_min_score=int(_env("DIGEST_MIN_SCORE", "55")),
        ntfy_url=_env("NTFY_URL"),
        hot_lead_score=int(_env("HOT_LEAD_SCORE", "80")),
        ollama_url=_env("OLLAMA_URL"),
        ollama_model=_env("OLLAMA_MODEL", "llama3.2:3b"),
        geocode_enabled=_env("GEOCODE", "1") not in ("0", "false", "no"),
        geocode_per_run=int(_env("GEOCODE_PER_RUN", "200")),
    )


def load_sources(path: Path | None = None) -> dict[str, dict]:
    """Return {source_id: config} for every source in sources.yaml (enabled or not)."""
    path = path or get_settings().sources_file
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    sources = data.get("sources") or {}
    for source_id, cfg in sources.items():
        cfg.update(_expand_env(cfg))
        cfg.setdefault("enabled", True)
        cfg.setdefault("name", source_id)
    return sources


def _expand_env(value):
    """Allow ${VAR} references in sources.yaml so passwords stay in .env."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value
