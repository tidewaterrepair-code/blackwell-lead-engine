"""Stripe subscriptions, add-ons, credit packs, the credit ledger, trials and referral commissions.

Stripe price IDs come from env (STRIPE_PRICE_PRO_MONTHLY, ...). Create the
products once in the Stripe dashboard (or `pegasus billing setup`) and paste the IDs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import BillingEvent, CreditLedger, Org, Referral
from .plans import CREDIT_PACKS, PLANS, effective_plan

log = logging.getLogger(__name__)


class BillingError(Exception):
    pass


class InsufficientCredits(BillingError):
    pass


# ---------------------------------------------------------------- credits

def add_credits(session: Session, org: Org, delta: int, reason: str, ref: str | None = None) -> int:
    org.credits = (org.credits or 0) + delta
    session.add(CreditLedger(org_id=org.id, delta=delta, balance_after=org.credits, reason=reason, ref=ref))
    return org.credits


def spend_credits(session: Session, org: Org, amount: int, reason: str, ref: str | None = None) -> int:
    if (org.credits or 0) < amount:
        raise InsufficientCredits(f"This needs {amount} credit(s); you have {org.credits or 0}.")
    return add_credits(session, org, -amount, reason, ref)


def grant_monthly_credits(session: Session) -> int:
    """Top up plan credits every 30 days for paying and trialing orgs (balance capped at 2x the plan grant)."""
    n = 0
    now = utcnow()
    for org in session.scalars(select(Org).where(Org.plan_status.in_(("active", "trialing")))):
        plan = effective_plan(org)
        if not plan.monthly_credits:
            continue
        last = (org.settings or {}).get("credits_granted_at")
        if last and datetime.fromisoformat(last) + timedelta(days=30) > now:
            continue
        grant = min(plan.monthly_credits, max(0, 2 * plan.monthly_credits - (org.credits or 0)))
        if org.plan_status == "trialing":
            grant = min(grant, 25)  # trials get a taste
        if grant:
            add_credits(session, org, grant, "monthly_grant", plan.key)
        org.settings = {**(org.settings or {}), "credits_granted_at": now.isoformat()}
        n += 1
    return n


def expire_trials(session: Session) -> int:
    n = 0
    for org in session.scalars(select(Org).where(Org.plan_status == "trialing", Org.trial_ends_at < utcnow())):
        if org.stripe_subscription_id:
            continue
        org.plan, org.plan_status = "free", "active"
        n += 1
    return n


# ---------------------------------------------------------------- Stripe

def _stripe():
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingError("Billing isn't configured yet (set STRIPE_SECRET_KEY).")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def price_for(key: str) -> str:
    price = get_settings().stripe_prices.get(key)
    if not price:
        raise BillingError(f"Missing Stripe price for {key} (set STRIPE_PRICE_{key.upper()}).")
    return price


def plan_for_price(price_id: str) -> tuple[str | None, str | None]:
    for key, value in get_settings().stripe_prices.items():
        if value == price_id:
            plan, _, interval = key.rpartition("_")
            if plan in PLANS:
                return plan, interval
            return key, None
    return None, None


def _customer(stripe, session: Session, org: Org, email: str) -> str:
    if not org.stripe_customer_id:
        customer = stripe.Customer.create(email=email, name=org.name, metadata={"org_id": str(org.id)})
        org.stripe_customer_id = customer["id"]
        session.flush()
    return org.stripe_customer_id


def checkout_url(session: Session, org: Org, email: str, item: str, interval: str = "monthly",
                 quantity: int = 1) -> str:
    """Stripe Checkout for a plan ('pro'...), an add-on ('territory_addon', 'exclusive_zip') or credits."""
    stripe = _stripe()
    base = get_settings().public_url
    customer = _customer(stripe, session, org, email)
    meta = {"org_id": str(org.id), "item": item}
    params: dict = {
        "customer": customer, "client_reference_id": str(org.id), "metadata": meta,
        "success_url": f"{base}/app/billing?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/app/billing?status=cancelled", "allow_promotion_codes": True,
        "automatic_tax": {"enabled": True}, "customer_update": {"address": "auto"},
    }
    if item in PLANS:
        if item == "free":
            raise BillingError("The free plan doesn't need checkout.")
        params["mode"] = "subscription"
        params["line_items"] = [{"price": price_for(f"{item}_{interval}"), "quantity": 1}]
        params["subscription_data"] = {"metadata": meta}
        coupon = get_settings_coupon()
        if org.founding_member and coupon:
            params["discounts"] = [{"coupon": coupon}]
            params.pop("allow_promotion_codes")
    elif item in ("territory_addon", "exclusive_zip"):
        params["mode"] = "subscription"
        params["line_items"] = [{"price": price_for(item), "quantity": max(1, quantity)}]
        params["subscription_data"] = {"metadata": meta}
    elif item in CREDIT_PACKS:
        params["mode"] = "payment"
        params["line_items"] = [{"price": price_for(item), "quantity": max(1, quantity)}]
        meta["credits"] = str(CREDIT_PACKS[item] * max(1, quantity))
    else:
        raise BillingError(f"Unknown billing item {item!r}.")
    return stripe.checkout.Session.create(**params)["url"]


def get_settings_coupon() -> str | None:
    from .config import _env

    return _env("STRIPE_COUPON_FOUNDING")


def portal_url(org: Org) -> str:
    stripe = _stripe()
    if not org.stripe_customer_id:
        raise BillingError("No billing account yet. Choose a plan first.")
    return stripe.billing_portal.Session.create(customer=org.stripe_customer_id,
                                                return_url=f"{get_settings().public_url}/app/billing")["url"]


def handle_webhook(session: Session, payload: bytes, signature: str | None) -> str:
    settings = get_settings()
    stripe = _stripe()
    if not settings.stripe_webhook_secret:
        raise BillingError("STRIPE_WEBHOOK_SECRET is not set.")
    try:
        stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise BillingError("Invalid webhook signature.") from exc
    # Signature verified; work with plain dicts rather than StripeObjects.
    return apply_event(session, json.loads(payload))


def _org_from(session: Session, obj: dict) -> Org | None:
    meta = obj.get("metadata") or {}
    org_id = meta.get("org_id") or obj.get("client_reference_id")
    if org_id:
        return session.get(Org, int(org_id))
    customer = obj.get("customer")
    if customer:
        return session.scalar(select(Org).where(Org.stripe_customer_id == customer))
    return None


def _mark_canceled(org: Org) -> None:
    """Remember when a paid plan ended (anchors the win-back email sequence)."""
    if not (org.settings or {}).get("canceled_at"):
        org.settings = {**(org.settings or {}), "canceled_at": utcnow().isoformat()}


def apply_event(session: Session, event: dict) -> str:
    """Apply one Stripe event (idempotent on event id)."""
    if session.get(BillingEvent, event["id"]):
        return "duplicate"
    etype, obj = event["type"], event["data"]["object"]
    org = _org_from(session, obj)
    amount = 0
    if etype == "checkout.session.completed" and org:
        meta, item = obj.get("metadata") or {}, (obj.get("metadata") or {}).get("item")
        if obj.get("mode") == "payment" and meta.get("credits"):
            add_credits(session, org, int(meta["credits"]), "purchase", obj.get("id"))
        elif item in PLANS:
            org.plan, org.plan_status = item, "active"
            org.stripe_subscription_id = obj.get("subscription") or org.stripe_subscription_id
        elif item == "territory_addon":
            org.settings = {**(org.settings or {}),
                            "extra_territories": int((org.settings or {}).get("extra_territories", 0)) + 1}
        elif item == "exclusive_zip":
            org.settings = {**(org.settings or {}), "exclusive_slots":
                            int((org.settings or {}).get("exclusive_slots", 0)) + 1}
    elif etype in ("customer.subscription.updated", "customer.subscription.created") and org:
        items = (obj.get("items") or {}).get("data") or []
        for it in items:
            plan, interval = plan_for_price((it.get("price") or {}).get("id", ""))
            if plan in PLANS:
                org.plan = plan
                org.stripe_subscription_id = obj.get("id")
                org.settings = {**(org.settings or {}), "interval": interval or "monthly"}
        status = obj.get("status")
        org.plan_status = {"active": "active", "trialing": "active", "past_due": "past_due",
                           "unpaid": "past_due", "canceled": "canceled",
                           "incomplete_expired": "canceled"}.get(status, org.plan_status)
        if org.plan_status == "canceled":
            _mark_canceled(org)
    elif etype == "customer.subscription.deleted" and org:
        if obj.get("id") == org.stripe_subscription_id:
            org.plan, org.plan_status, org.stripe_subscription_id = "free", "active", None
            _mark_canceled(org)
    elif etype == "invoice.paid" and org:
        amount = int(obj.get("amount_paid") or 0)
        ref = session.scalar(select(Referral).where(Referral.referred_org_id == org.id))
        if ref and amount:
            ref.status = "paying"
            ref.commission_cents += round(amount * ref.commission_rate)
    elif etype == "invoice.payment_failed" and org:
        org.plan_status = "past_due"
    session.add(BillingEvent(id=event["id"], type=etype, org_id=org.id if org else None, amount_cents=amount))
    return etype
