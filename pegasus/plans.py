"""Plans, limits and features. Prices here are display prices; Stripe price IDs come from env."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .db import utcnow

TRIAL_DAYS = 14
TRIAL_PLAN = "growth"
FOUNDING_DISCOUNT = 0.40
FOUNDING_SEATS = 100
CREDIT_PRICE_CENTS = 25  # one skip trace = 1 credit
CREDIT_PACKS = {"credits_25": 100, "credits_100": 450, "credits_250": 1250}  # price key -> credits
REFERRAL_RATE = 0.30
EXTRA_TERRITORY_PRICE = 29
EXCLUSIVE_ZIP_PRICE = 149


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    monthly: int
    annual: int  # per year
    tagline: str
    trades: int
    territories: int
    seats: int
    monthly_credits: int
    lead_delay_days: int = 0
    monthly_lead_cap: int | None = None
    max_radius_miles: int = 150
    features: frozenset[str] = field(default_factory=frozenset)
    highlights: tuple[str, ...] = ()


BASE = {"leads", "pipeline", "map"}
PRO = BASE | {"alerts", "csv_export", "realtime", "notes", "contacts"}
GROWTH = PRO | {"predictions", "ai_briefs", "deal_analyzer", "likely_to_sell", "crm_sync", "team", "storm_alerts"}
ELITE = GROWTH | {"mls", "farm_reports", "market_reports", "expired_listings"}
TEAM = ELITE | {"api", "white_label", "admin_reports", "exclusive_territories"}

PLANS: dict[str, Plan] = {
    "free": Plan("free", "Scout", 0, 0, "Kick the tires", trades=1, territories=1, seats=1,
                 monthly_credits=0, lead_delay_days=7, monthly_lead_cap=15, max_radius_miles=10,
                 features=frozenset(BASE),
                 highlights=("1 trade, 1 small area", "15 leads / month", "Leads arrive 7 days late", "Weekly email")),
    "pro": Plan("pro", "Pro", 79, 790, "For the solo pro", trades=1, territories=1, seats=1,
                monthly_credits=50, max_radius_miles=40, features=frozenset(PRO),
                highlights=("Unlimited real-time leads", "1 trade, 1 county or 40-mile radius",
                            "Instant alerts & daily digest", "50 contact credits / month")),
    "growth": Plan("growth", "Growth", 179, 1790, "Most popular", trades=3, territories=3, seats=5,
                   monthly_credits=250, features=frozenset(GROWTH),
                   highlights=("Predicted jobs before they're permitted", "3 trades, 3 areas, 5 seats",
                               "AI lead briefs & outreach scripts", "Storm alerts, deal analyzer",
                               "250 contact credits / month")),
    "elite": Plan("elite", "Agent Elite", 249, 2490, "For top-producing agents", trades=3, territories=5,
                  seats=2, monthly_credits=400, features=frozenset(ELITE),
                  highlights=("Connect your MLS", "Likely-to-sell & distress stack", "Expired / withdrawn / FSBO",
                              "Branded market reports", "400 contact credits / month")),
    "team": Plan("team", "Team", 799, 7990, "Brokerages, builders & suppliers", trades=10, territories=15,
                 seats=25, monthly_credits=2000, features=frozenset(TEAM),
                 highlights=("25 seats, 15 areas", "Exclusive ZIP territories", "API & white-label reports",
                             "2,000 contact credits / month")),
}
PAID_PLANS = ("pro", "growth", "elite", "team")


def get_plan(org) -> Plan:
    return PLANS.get(org.plan, PLANS["free"])


def effective_plan(org) -> Plan:
    """Trial and paid orgs get their plan; lapsed ones fall back to free."""
    if org.plan_status in ("active", "trialing", "past_due"):
        if org.plan_status == "trialing" and org.trial_ends_at and org.trial_ends_at < utcnow():
            return PLANS["free"]
        return get_plan(org)
    return PLANS["free"]


def has_feature(org, feature: str) -> bool:
    return feature in effective_plan(org).features


def start_trial(org) -> None:
    org.plan, org.plan_status = TRIAL_PLAN, "trialing"
    org.trial_ends_at = utcnow() + timedelta(days=TRIAL_DAYS)


def founding_price(plan: Plan) -> int:
    return round(plan.monthly * (1 - FOUNDING_DISCOUNT))


def public_catalog() -> list[dict]:
    return [
        {
            "key": p.key, "label": p.label, "monthly": p.monthly, "annual": p.annual, "tagline": p.tagline,
            "highlights": list(p.highlights), "trades": p.trades, "territories": p.territories, "seats": p.seats,
            "credits": p.monthly_credits, "features": sorted(p.features), "founding_monthly": founding_price(p),
        }
        for p in PLANS.values()
    ]
