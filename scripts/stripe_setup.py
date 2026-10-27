"""Create Pegasus's Stripe catalog and webhook, then write the IDs into .env.

Safe to re-run: prices are found by lookup_key, the coupon by id and the webhook by URL.
Reads STRIPE_SECRET_KEY from .env and never prints it.

    .venv/bin/python scripts/stripe_setup.py [--env .env]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import stripe

PLANS = {"pro": ("Pegasus Pro", 79, 790), "growth": ("Pegasus Growth", 179, 1790),
         "elite": ("Pegasus Agent Elite", 249, 2490), "team": ("Pegasus Team", 799, 7990)}
ADDONS = {"territory_addon": ("Pegasus Extra Territory", 29), "exclusive_zip": ("Pegasus Exclusive ZIP", 149)}
CREDITS = {"credits_25": ("Pegasus Credits: 100", 25), "credits_100": ("Pegasus Credits: 450", 100),
           "credits_250": ("Pegasus Credits: 1,250", 250)}
COUPON_ID = "FOUNDING40"
WEBHOOK_EVENTS = ["checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
                  "customer.subscription.deleted", "invoice.paid", "invoice.payment_failed"]


def env_get(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*(?:export\s+)?{key}=([^\s#]*)", text, re.M)
    return m.group(1) if m and m.group(1) else None


def env_set(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^\s*(?:export\s+)?{key}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(f"{key}={value}", text, count=1)
    return text.rstrip("\n") + f"\n{key}={value}\n"


def product(name: str, key: str) -> str:
    found = stripe.Product.search(query=f"metadata['pegasus_key']:'{key}'").data
    if found:
        return found[0].id
    return stripe.Product.create(name=name, metadata={"pegasus_key": key}).id


def price(lookup: str, product_id: str, dollars: int, interval: str | None) -> str:
    found = stripe.Price.list(lookup_keys=[lookup], limit=1).data
    if found:
        return found[0].id
    params = {"product": product_id, "currency": "usd", "unit_amount": dollars * 100, "lookup_key": lookup,
              "tax_behavior": "exclusive"}
    if interval:
        params["recurring"] = {"interval": interval}
    return stripe.Price.create(**params).id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=".env")
    ap.add_argument("--url", help="webhook URL (default: PUBLIC_URL/api/stripe/webhook)")
    args = ap.parse_args()
    path = Path(args.env)
    text = path.read_text()
    stripe.api_key = env_get(text, "STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise SystemExit("STRIPE_SECRET_KEY is not set in " + str(path))
    mode = "live" if "_live_" in stripe.api_key else "test"
    print(f"Stripe {mode} mode")

    ids: dict[str, str] = {}
    for key, (name, monthly, annual) in PLANS.items():
        pid = product(name, key)
        ids[f"{key}_monthly"] = price(f"pegasus_{key}_monthly", pid, monthly, "month")
        ids[f"{key}_annual"] = price(f"pegasus_{key}_annual", pid, annual, "year")
    for key, (name, dollars) in ADDONS.items():
        ids[key] = price(f"pegasus_{key}", product(name, key), dollars, "month")
    for key, (name, dollars) in CREDITS.items():
        ids[key] = price(f"pegasus_{key}", product(name, key), dollars, None)

    try:
        stripe.Coupon.retrieve(COUPON_ID)
    except stripe.InvalidRequestError:
        stripe.Coupon.create(id=COUPON_ID, name="Founding member (40% for life)", percent_off=40,
                             duration="forever")

    url = args.url or (env_get(text, "PUBLIC_URL") or "").rstrip("/") + "/api/stripe/webhook"
    hook = next((w for w in stripe.WebhookEndpoint.list(limit=100).data if w.url == url), None)
    if hook:
        stripe.WebhookEndpoint.modify(hook.id, enabled_events=WEBHOOK_EVENTS)
        print(f"webhook exists: {url} (kept its existing secret)")
    else:
        hook = stripe.WebhookEndpoint.create(url=url, enabled_events=WEBHOOK_EVENTS,
                                             description="Pegasus billing")
        text = env_set(text, "STRIPE_WEBHOOK_SECRET", hook.secret)
        print(f"webhook created: {url}")

    for key, value in ids.items():
        text = env_set(text, f"STRIPE_PRICE_{key.upper()}", value)
        print(f"  STRIPE_PRICE_{key.upper()}={value}")
    text = env_set(text, "STRIPE_COUPON_FOUNDING", COUPON_ID)
    path.write_text(text)
    print(f"  STRIPE_COUPON_FOUNDING={COUPON_ID}\nWrote {path}")


if __name__ == "__main__":
    main()
