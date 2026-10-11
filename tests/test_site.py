import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import NORFOLK, ingest


@pytest.fixture
def client():
    from pegasus.web.app import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/pricing", "/for/framer", "/for/real-estate-agent", "/legal/terms",
                                  "/legal/privacy", "/legal/acceptable-use", "/legal/data-sources", "/optout",
                                  "/robots.txt", "/sitemap.xml"])
def test_public_pages(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text[:300]


def test_landing_has_founding_offer_and_plans(client):
    html = client.get("/").text
    assert "100 seats left" in html and "Most popular" in html and "$107" in html  # growth founding price


def test_unknown_pages_render_branded_404(client):
    r = client.get("/for/astronaut")
    assert r.status_code == 404 and "flew off" in r.text
    assert client.get("/leads/va/nowhere").status_code == 404


def test_seo_city_page_hides_house_numbers(client, fixture_text):
    ingest("nor", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
    r = client.get("/leads/va/norfolk")
    assert r.status_code == 200
    assert "Little Creek" in r.text and "1214" not in r.text
    assert client.get("/leads/va/norfolk/deck").status_code == 200
    assert "/leads/va/norfolk" in client.get("/sitemap.xml").text


def test_optout_is_recorded(client):
    from sqlalchemy import select

    from pegasus.db import session_scope
    from pegasus.models import OptOut

    r = client.post("/optout", data={"address": "5 Elm St, Norfolk", "phone": "(757) 555-0100"})
    assert r.status_code == 200 and "Done" in r.text
    with session_scope() as s:
        row = s.scalars(select(OptOut)).one()
        assert row.phone == "7575550100" and row.norm_address == "5 elm st"


def test_market_report_requires_elite(client):
    from tests.test_api import H, signup

    signup(client, trades=("real_estate_agent",))
    tid = client.post("/api/territories", json={"kind": "zip", "data": {"zips": ["23451"]}}, headers=H).json()["territory"]["id"]
    assert client.get(f"/reports/market/{tid}").status_code == 402  # trial is Growth: reports are Elite
    from sqlalchemy import select

    from pegasus.db import session_scope
    from pegasus.models import Org

    with session_scope() as s:
        s.scalars(select(Org)).one().plan = "elite"
    r = client.get(f"/reports/market/{tid}")
    assert r.status_code == 200 and "Market report" in r.text
