import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pegasus.db import session_scope
from pegasus.models import Org, OrgLead
from tests.conftest import VB_NORFOLK_COUNTIES

H = {"X-Pegasus": "1"}


@pytest.fixture
def app():
    from pegasus.web.app import create_app

    return create_app()


def signup(client, email="dee@decks.com", trades=("deck_builder", "framer"), **extra):
    body = {"email": email, "password": "supersecret1", "name": "Dee", "org_name": "Dee Decks", "trades": list(trades),
            **extra}
    r = client.post("/api/auth/signup", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def test_signup_me_and_trial(client):
    signup(client)
    me = client.get("/api/me").json()
    assert me["org"]["plan"] == "growth" and me["org"]["plan_status"] == "trialing"
    assert "predictions" in me["plan"]["features"]
    assert me["user"]["streak"] == 1 and me["org"]["founding_member"] is True
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/me").status_code == 401


def test_login_and_bad_password(client):
    signup(client)
    client.post("/api/auth/logout", headers=H)
    assert client.post("/api/auth/login", json={"email": "dee@decks.com", "password": "nope"}, headers=H).status_code == 400
    assert client.post("/api/auth/login", json={"email": "DEE@decks.com", "password": "supersecret1"},
                       headers=H).status_code == 200


def test_magic_link_flow(client):
    from pegasus.notify import OUTBOX

    signup(client)
    client.post("/api/auth/logout", headers=H)
    assert client.post("/api/auth/magic", json={"email": "dee@decks.com"}, headers=H).json() == {"ok": True}
    assert client.post("/api/auth/magic", json={"email": "nobody@x.com"}, headers=H).json() == {"ok": True}
    assert len(OUTBOX) == 1
    link = next(w for w in OUTBOX[0]["text"].split() if "token=" in w)
    r = client.get(link.replace("http://localhost:8000", ""), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    assert client.get("/api/me").status_code == 200


def test_csrf_header_required(client):
    r = client.post("/api/auth/signup", json={"email": "a@b.co", "password": "supersecret1", "trades": ["framer"]})
    assert r.status_code == 403


def test_territory_coverage_and_leads_feed(client, norfolk_vb):
    signup(client)
    r = client.post("/api/territories", json={"kind": "county", "data": {"fips": ["51810", "51710"]}}, headers=H)
    assert r.status_code == 200, r.text
    norfolk_vb()
    feed = client.get("/api/leads").json()
    assert feed["total"] >= 3
    first = feed["items"][0]
    assert first["score"] >= feed["items"][-1]["score"]
    detail = client.get(f"/api/leads/{first['id']}").json()
    assert "next_jobs" in detail and "history" in detail
    preds = client.get("/api/leads?type=prediction").json()["items"]
    assert preds and preds[0]["prediction"]["reason"]
    stats = client.get("/api/stats").json()
    assert stats["new_24h"] >= 3 and stats["radar"]
    assert client.get("/api/map").json()["points"]


def test_pipeline_actions_award_xp_badges_and_celebrate(client, norfolk_vb):
    signup(client)
    client.post("/api/territories", json=VB_NORFOLK_COUNTIES, headers=H)
    norfolk_vb()
    lead_id = client.get("/api/leads?type=signal").json()["items"][0]["id"]
    r = client.patch(f"/api/leads/{lead_id}", json={"status": "contacted"}, headers=H).json()
    assert "First contact" in r["badges"] and r["xp"] >= 10
    client.post(f"/api/leads/{lead_id}/notes", json={"body": "Left voicemail", "kind": "call"}, headers=H)
    r = client.patch(f"/api/leads/{lead_id}", json={"status": "won", "value_won": 24000}, headers=H).json()
    assert r["celebrate"] is True and "Closer: first win" in r["badges"]
    detail = client.get(f"/api/leads/{lead_id}").json()
    assert any(a["body"] == "Left voicemail" for a in detail["activities"])
    assert client.get("/api/stats").json()["won_this_month"] == 24000


def test_tenant_isolation(app, norfolk_vb):
    with TestClient(app) as a, TestClient(app) as b:
        signup(a, "a@x.com")
        a.post("/api/territories", json=VB_NORFOLK_COUNTIES, headers=H)
        signup(b, "b@x.com")
        norfolk_vb()
        a_lead = a.get("/api/leads").json()["items"][0]["id"]
        assert b.get(f"/api/leads/{a_lead}").status_code == 404
        assert b.patch(f"/api/leads/{a_lead}", json={"status": "won"}, headers=H).status_code == 404
        manual = a.post("/api/leads", json={"title": "Neighbor wants a 16x20 deck", "address": "4 Elm St",
                                            "city": "Norfolk", "state": "VA"}, headers=H).json()
        assert manual["status"] == "saved"
        assert b.get(f"/api/leads/{manual['id']}").status_code == 404
        assert all(i["id"] != manual["id"] for i in b.get("/api/leads?status=all").json()["items"])


def test_predictions_are_locked_on_pro(client, norfolk_vb):
    signup(client)
    client.post("/api/territories", json=VB_NORFOLK_COUNTIES, headers=H)
    with session_scope() as s:
        org = s.scalars(select(Org)).first()
        org.plan, org.plan_status = "pro", "active"
    norfolk_vb()
    pred = client.get("/api/leads?type=prediction").json()["items"][0]
    assert pred["locked"] is True and pred["signal"]["address"] is None
    r = client.patch(f"/api/leads/{pred['id']}", json={"status": "saved"}, headers=H)
    assert r.status_code == 402


def test_plan_limits_on_territories_and_trades(client):
    signup(client)
    for i in range(3):
        assert client.post("/api/territories", json={"kind": "zip", "data": {"zips": [f"2345{i}"]}},
                           headers=H).status_code == 200
    r = client.post("/api/territories", json={"kind": "zip", "data": {"zips": ["23460"]}}, headers=H)
    assert r.status_code == 400 and "area" in r.json()["message"]
    r = client.patch("/api/org", json={"trades": ["framer", "roofer", "hvac", "plumber"]}, headers=H)
    assert r.status_code == 400


def test_recap_share_rewards_once_per_week(client):
    signup(client)
    assert client.post("/api/recap/share", headers=H).json()["awarded"] == 5
    assert client.post("/api/recap/share", headers=H).json()["awarded"] == 0
    assert client.get("/api/recap").json()["share_url"].startswith("/r/")


def test_team_invite_and_join(app):
    from pegasus.notify import OUTBOX

    with TestClient(app) as owner, TestClient(app) as newbie:
        signup(owner)
        assert owner.post("/api/team/invite", json={"email": "crew@decks.com"}, headers=H).status_code == 200
        link = next(w for w in OUTBOX[-1]["text"].split() if "invite=" in w)
        token = link.split("invite=")[1]
        r = newbie.post("/api/auth/signup", json={"email": "crew@decks.com", "password": "supersecret1",
                                                  "invite": token}, headers=H)
        assert r.status_code == 200
        assert newbie.get("/api/me").json()["org"]["name"] == "Dee Decks"
        assert len(owner.get("/api/team").json()["members"]) == 2


def test_catalog_geo_and_csv_gate(client):
    cat = client.get("/api/catalog").json()
    assert any(t["key"] == "real_estate_agent" for t in cat["trades"]) and len(cat["plans"]) == 5
    results = client.get("/api/geo/search?q=virginia beach").json()["results"]
    assert any(r["type"] == "city" for r in results)
    assert client.get("/api/geo/search?q=23456").json()["results"][0]["county_fips"] == "51810"
    signup(client)
    assert client.get("/api/leads.csv").status_code == 200  # trial = growth includes CSV


def test_admin_requires_platform_admin(app):
    with TestClient(app) as c:
        signup(c, "nobody@x.com")
        assert c.get("/api/admin/overview").status_code == 404
    with TestClient(app) as boss:
        signup(boss, "boss@pegasus.test")
        data = boss.get("/api/admin/overview").json()
        assert data["customers"]["total"] == 2 and "mrr" in data


def test_brief_falls_back_to_template_without_ai(client, norfolk_vb):
    signup(client)
    client.post("/api/territories", json=VB_NORFOLK_COUNTIES, headers=H)
    norfolk_vb()
    lead_id = client.get("/api/leads?type=signal").json()["items"][0]["id"]
    brief = client.post(f"/api/leads/{lead_id}/brief", headers=H).json()
    assert brief["source"] == "template" and "opener" in brief and len(brief["talking_points"]) == 3


def test_waitlist_and_referral(client):
    assert client.post("/api/waitlist", json={"email": "pro@trade.com", "audience": "trades"}).json() == {"ok": True}
    signup(client)
    code = client.get("/api/me").json()["org"]["referral_code"]
    r = client.get(f"/r/{code}", follow_redirects=False)
    assert r.status_code == 303 and f"ref={code}" in r.headers["location"]
    with session_scope() as s:
        assert s.scalars(select(OrgLead)).all() == []
