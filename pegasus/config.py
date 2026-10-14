"""Runtime settings (environment variables) and the seed sources.yaml loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() not in ("0", "false", "no", "off")


@dataclass
class Settings:
    env: str
    data_dir: Path
    database_url: str
    sources_file: Path
    secret_key: str
    public_url: str
    admin_emails: set[str]
    # Email (transactional: magic links, digests, alerts).
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    mail_from: str
    # AI (pay as you go). Without a key, rules + templates are used instead.
    anthropic_api_key: str | None
    ai_fast_model: str
    ai_smart_model: str
    ollama_url: str | None
    ollama_model: str
    # Billing.
    stripe_secret_key: str | None
    stripe_webhook_secret: str | None
    stripe_prices: dict[str, str]
    # Data providers (pay as you grow).
    batchdata_api_key: str | None
    regrid_token: str | None
    socrata_app_token: str | None
    # Scheduling.
    ingest_hours: str
    digest_hour: int
    lookback_days: int
    geocode_enabled: bool
    geocode_per_run: int
    ntfy_base_url: str
    user_agent: str = "PegasusLeadBot/1.0 (+https://getpegasus.org/bot)"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)


STRIPE_PRICE_KEYS = (
    "pro_monthly", "pro_annual", "growth_monthly", "growth_annual", "elite_monthly", "elite_annual",
    "team_monthly", "team_annual", "territory_addon", "exclusive_zip", "credits_25", "credits_100", "credits_250",
)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(_env("PEGASUS_DATA_DIR", _env("LEADENGINE_DATA_DIR", "data"))).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        env=_env("PEGASUS_ENV", "development"),
        data_dir=data_dir,
        database_url=_env("DATABASE_URL", f"sqlite:///{data_dir / 'pegasus.db'}"),
        sources_file=Path(_env("SOURCES_FILE", "sources.yaml")).resolve(),
        secret_key=_env("SECRET_KEY", "dev-insecure-change-me"),
        public_url=_env("PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        admin_emails={e.strip().lower() for e in (_env("ADMIN_EMAILS", "") or "").split(",") if e.strip()},
        smtp_host=_env("SMTP_HOST"),
        smtp_port=int(_env("SMTP_PORT", "587")),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        mail_from=_env("MAIL_FROM", _env("SMTP_USER", "Pegasus <hello@getpegasus.org>")),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        ai_fast_model=_env("AI_FAST_MODEL", "claude-opus-5-5"),
        ai_smart_model=_env("AI_SMART_MODEL", "claude-opus-5-5"),
        ollama_url=_env("OLLAMA_URL"),
        ollama_model=_env("OLLAMA_MODEL", "llama3.2:3b"),
        stripe_secret_key=_env("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=_env("STRIPE_WEBHOOK_SECRET"),
        stripe_prices={k: v for k in STRIPE_PRICE_KEYS if (v := _env(f"STRIPE_PRICE_{k.upper()}"))},
        batchdata_api_key=_env("BATCHDATA_API_KEY"),
        regrid_token=_env("REGRID_TOKEN"),
        socrata_app_token=_env("SOCRATA_APP_TOKEN"),
        ingest_hours=_env("INGEST_HOURS", "5,11,17"),
        digest_hour=int(_env("DIGEST_HOUR", "7")),
        lookback_days=int(_env("LOOKBACK_DAYS", "30")),
        geocode_enabled=_env_bool("GEOCODE", True),
        geocode_per_run=int(_env("GEOCODE_PER_RUN", "500")),
        ntfy_base_url=_env("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/"),
    )


def load_sources(path: Path | None = None) -> dict[str, dict]:
    """Return {source_id: config} for every source in the seed sources.yaml."""
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
