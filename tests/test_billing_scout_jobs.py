import json
import time
from datetime import timedelta

import httpx
from sqlalchemy import select

from pegasus.db import session_scope, utcnow
from pegasus.models import BillingEvent, CreditLedger, Job, Org, Referral, ScoutJob, Source


# ---------------------------------------------------------------- billing

def org_with_referrer():
    from pegasus.accounts import signup

    with session_scope() as s:
        _, ref_org = signup(s, email="coach@x.com", password="supersecret1", name=None, org_name=None,
                            trades=["remodeler"])
        _, org = signup(s, email="new@x.com", password="supersecret1", name=None, org_name=None, trades=["roofer"],
                        ref=ref_org.referral_code)
        return org.id, ref_org.id


def event(eid, etype, obj):
    return {"id": eid, "type": etype, "data": {"object": obj}}


def test_checkout_subscription_credits_and_addons(monkeypatch):
    from pegasus.billing import apply_event

    org_id, _ = org_with_referrer()
    with session_scope() as s:
        apply_event(s, event("evt_1", "checkout.session.completed",
                             {"mode": "subscription", "metadata": {"org_id": str(org_id), "item": "pro"},
                              "subscription": "sub_1", "customer": "cus_1"}))
        apply_event(s, event("evt_2", "checkout.session.completed",
                             {"mode": "payment", "metadata": {"org_id": str(org_id), "credits": "450"}, "id": "cs_2"}))
        apply_event(s, event("evt_3", "checkout.session.completed",
                             {"mode": "subscription", "metadata": {"org_id": str(org_id), "item": "territory_addon"}}))
        assert apply_event(s, event("evt_3", "checkout.session.completed", {})) == "duplicate"
        org = s.get(Org, org_id)
        assert (org.plan, org.plan_status, org.stripe_subscription_id) == ("pro", "active", "sub_1")
        assert org.credits == 450 and org.settings["extra_territories"] == 1
        assert s.scalar(select(CreditLedger).where(CreditLedger.reason == "purchase")).delta == 450


def test_subscription_lifecycle_and_referral_commission(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_GROWTH_ANNUAL", "price_growth_y")
    from pegasus.config import get_settings

    get_settings.cache_clear()
    from pegasus.billing import apply_event

    try:
        org_id, ref_org = org_with_referrer()
        with session_scope() as s:
            org = s.get(Org, org_id)
            org.stripe_customer_id = "cus_9"
            apply_event(s, event("e1", "customer.subscription.updated",
                                 {"id": "sub_9", "customer": "cus_9", "status": "active",
                                  "items": {"data": [{"price": {"id": "price_growth_y"}}]}}))
            assert (org.plan, org.plan_status, org.settings["interval"]) == ("growth", "active", "annual")
            apply_event(s, event("e2", "invoice.paid", {"customer": "cus_9", "amount_paid": 179000}))
            ref = s.scalar(select(Referral).where(Referral.referred_org_id == org_id))
            assert ref.referrer_org_id == ref_org and ref.commission_cents == 53700 and ref.status == "paying"
            apply_event(s, event("e3", "invoice.payment_failed", {"customer": "cus_9"}))
            assert org.plan_status == "past_due"
            apply_event(s, event("e4", "customer.subscription.deleted", {"id": "sub_9", "customer": "cus_9"}))
            assert (org.plan, org.plan_status) == ("free", "active")
            assert s.get(BillingEvent, "e2").amount_cents == 179000
    finally:
        get_settings.cache_clear()


def test_webhook_signature_is_verified(monkeypatch):
    import stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    from pegasus.config import get_settings

    get_settings.cache_clear()
    try:
        from fastapi.testclient import TestClient

        from pegasus.web.app import create_app

        org_id, _ = org_with_referrer()
        payload = json.dumps(event("evt_sig", "checkout.session.completed",
                                   {"mode": "payment", "metadata": {"org_id": str(org_id), "credits": "100"},
                                    "id": "cs_sig"}))
        ts = int(time.time())
        sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload}", "whsec_test")
        with TestClient(create_app()) as c:
            assert c.post("/api/stripe/webhook", content=payload,
                          headers={"stripe-signature": f"t={ts},v1=bad"}).status_code == 400
            r = c.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": f"t={ts},v1={sig}"})
            assert r.status_code == 200, r.text
        with session_scope() as s:
            assert s.get(Org, org_id).credits == 100
    finally:
        get_settings.cache_clear()


def test_trials_expire_and_monthly_credits_are_granted():
    from pegasus.billing import expire_trials, grant_monthly_credits

    org_id, _ = org_with_referrer()
    with session_scope() as s:
        org = s.get(Org, org_id)
        assert grant_monthly_credits(s) == 2
        assert org.credits == 25  # trial taste
        assert grant_monthly_credits(s) == 0  # not again within 30 days
        org.trial_ends_at = utcnow() - timedelta(hours=1)
        assert expire_trials(s) == 2 or org.plan == "free"
        assert (org.plan, org.plan_status) == ("free", "active")


# ---------------------------------------------------------------- jobs

def test_job_queue_unique_retry_and_failure():
    from pegasus.jobs import HANDLERS, enqueue, job, run_one

    calls = []

    @job("test_flaky")
    def flaky(payload):
        calls.append(payload)
        raise RuntimeError("boom")

    try:
        with session_scope() as s:
            assert enqueue(s, "test_flaky", {"n": 1}, unique_key="k", max_attempts=2)
            assert enqueue(s, "test_flaky", {"n": 2}, unique_key="k") is None
        assert run_one() is True
        with session_scope() as s:
            j = s.scalars(select(Job)).one()
            assert j.status == "queued" and j.attempts == 1 and "boom" in j.last_error
            j.run_at = utcnow()
        run_one()
        with session_scope() as s:
            assert s.scalars(select(Job)).one().status == "failed"
        assert len(calls) == 2 and run_one() is False
    finally:
        HANDLERS.pop("test_flaky", None)


# ---------------------------------------------------------------- source scout

def scout_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "api.us.socrata.com" in url:
        q = request.url.params.get("q", "")
        if "building permits" in q:
            return httpx.Response(200, json={"results": [{
                "resource": {"id": "abcd-1234", "name": "Building Permits Issued", "description": "Chesapeake permits",
                             "columns_field_name": ["permit_no", "work_desc", "site_address", "issue_date"]},
                "metadata": {"domain": "data.cityofchesapeake.net"}}]})
        return httpx.Response(200, json={"results": []})
    if "hub.arcgis.com" in url:
        return httpx.Response(200, json={"features": []})
    if "data.cityofchesapeake.net/resource/abcd-1234.json" in url:
        today = utcnow().strftime("%Y-%m-%dT00:00:00.000")
        return httpx.Response(200, json=[
            {"permit_no": f"P{i}", "work_desc": desc, "site_address": f"{i} Battlefield Blvd", "issue_date": today}
            for i, desc in enumerate(["New deck 12x16", "New single family dwelling", "Kitchen remodel",
                                      "Reroof", "Bathroom remodel"], start=1)])
    return httpx.Response(404)


def test_source_scout_discovers_maps_validates_and_proposes(monkeypatch):
    from pegasus.scout.runner import approve_source, pending_sources, scout

    monkeypatch.setattr("pegasus.scout.runner.AUTO_APPROVE_AT", 2.0)  # force human review
    out = scout("51550", client=httpx.Client(transport=httpx.MockTransport(scout_handler)))
    assert out["candidates"] == 1 and out["pending_review"] == 1
    pending = pending_sources()
    assert pending[0]["type"] == "socrata" and pending[0]["confidence"] >= 0.7
    with session_scope() as s:
        src = s.get(Source, pending[0]["id"])
        assert src.config["dataset"] == "abcd-1234" and src.config["fields"]["address"] == "site_address"
        assert src.config["county_fips"] == "51550"
        assert s.scalars(select(ScoutJob)).one().status == "review"
    approve_source(pending[0]["id"])
    with session_scope() as s:
        assert s.get(Source, pending[0]["id"]).status == "active"
        assert s.scalar(select(Job).where(Job.name == "scrape_source")) is not None


def test_territory_in_uncovered_county_queues_scout():
    from tests.conftest import make_org

    make_org("far@x.com", ["roofer"], {"kind": "county", "data": {"fips": ["48201"]}})  # Harris County, TX
    with session_scope() as s:
        jobs = s.scalars(select(Job).where(Job.name == "scout_jurisdiction")).all()
        assert [j.payload["fips"] for j in jobs] == ["48201"]


# ---------------------------------------------------------------- predictions & learning

def test_forecast_new_home_sequence_orders_trades():
    from pegasus.intel.predict import forecast

    now = utcnow()
    fcs = forecast(["new_construction"], "permit", now)
    trades = [f.trade for f in fcs]
    assert trades.index("concrete") < trades.index("framer") < trades.index("flooring") < trades.index("landscaper")
    pool = forecast(["pool"], "permit", now)
    assert any(f.trade == "fence" and "barrier" in f.reason for f in pool)


def test_learning_loop_reweights_predictions():
    from pegasus.intel.learn import learn_timelines, load_weights
    from tests.conftest import NORFOLK, VB_NORFOLK_COUNTIES, ingest, make_org
    from pegasus.models import OrgLead

    _, org = make_org("framer@x.com", ["framer"], VB_NORFOLK_COUNTIES)
    rows = [{"permit_number": f"N{i}", "address": f"{i} Oak St", "type": "Building", "work_type": "New",
             "structure": "Single Family Dwelling", "issue_date": utcnow().strftime("%Y-%m-%d")} for i in range(1, 9)]
    ingest("nor", NORFOLK, rows)
    with session_scope() as s:
        preds = s.scalars(select(OrgLead).where(OrgLead.org_id == org, OrgLead.lead_type == "prediction")).all()
        for lead in preds:
            lead.status = "passed"
        report = learn_timelines(s)
    with session_scope() as s:
        weights = load_weights(s)
    assert report["new_home_sequence:framer"]["misses"] == len(preds)
    assert weights["new_home_sequence:framer"] < 1.0
