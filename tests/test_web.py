import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from leadengine.pipeline import run_source
from tests.test_pipeline import NORFOLK, VB, _client


@pytest.fixture
def client(fixture_text):
    run_source("norfolk-permits", NORFOLK, client=_client(json.loads(fixture_text("norfolk_socrata.json"))))
    run_source("vb-permits", VB, client=_client(json.loads(fixture_text("vb_arcgis.json"))))
    from leadengine.web.app import app

    return TestClient(app)


def csrf_of(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


@pytest.mark.parametrize("path", ["/", "/map", "/pipeline", "/builders", "/bids", "/add", "/sources",
                                  "/?job_type=deck", "/?sort=value&status=all", "/api/leads.geojson",
                                  "/export.csv", "/healthz"])
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text[:500]


def test_feed_lists_leads_best_first(client):
    html = client.get("/").text
    assert "1214 W Little Creek Rd" in html
    assert "Reroof" not in html
    geo = client.get("/api/leads.geojson").json()
    assert len(geo["features"]) >= 4


def test_status_note_and_add_flow(client):
    page = client.get("/add").text
    token = csrf_of(page)
    resp = client.post("/add", data={"csrf": token, "title": "Screened porch for the Hendersons",
                                     "phone": "757-555-0111", "kind": "manual", "customer_type": "homeowner"},
                       follow_redirects=False)
    assert resp.status_code == 303
    url = resp.headers["location"]
    lead_id = url.rsplit("/", 1)[1]
    assert "Deck / porch" in client.get(url).text

    client.post(f"/leads/{lead_id}/status", data={"csrf": token, "status": "quoted"})
    client.post(f"/leads/{lead_id}/note", data={"csrf": token, "body": "Quoted $14,200", "kind": "quote"})
    html = client.get(url).text
    assert "Quoted $14,200" in html
    assert "Screened porch for the Hendersons" in client.get("/pipeline").text


def test_csrf_required(client):
    resp = client.post("/leads/1/status", data={"csrf": "nope", "status": "won"})
    assert resp.status_code == 400


def test_password_protection(monkeypatch, fixture_text):
    from leadengine.web import app as webapp

    monkeypatch.setattr(webapp.settings, "app_password", "s3cret")
    c = TestClient(webapp.app)
    resp = c.get("/", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"].startswith("/login")
    token = csrf_of(c.get("/login").text)
    assert "Wrong password" in c.post("/login", data={"csrf": token, "password": "x"}).text
    resp = c.post("/login", data={"csrf": token, "password": "s3cret", "next": "/bids"}, follow_redirects=False)
    assert resp.headers["location"] == "/bids"
    assert c.get("/").status_code == 200
