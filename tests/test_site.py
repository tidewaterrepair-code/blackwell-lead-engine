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


def test_homepage_structured_data_and_meta(client):
    import re

    html = client.get("/").text
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    graph = json.loads(blocks[0])["@graph"]
    types = {g["@type"] for g in graph}
    assert {"Organization", "WebSite", "SoftwareApplication", "FAQPage"} <= types
    app = next(g for g in graph if g["@type"] == "SoftwareApplication")
    assert app["offers"]["lowPrice"] == 79 and "aggregateRating" not in app  # never invent reviews
    faq = next(g for g in graph if g["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) >= 6
    assert html.count("<h1") == 1 and "Construction Leads" in re.search(r"<title>(.*?)</title>", html).group(1)
    assert 'property="og:url"' in html and 'name="twitter:title"' in html
    assert not re.findall(r"<img(?![^>]*alt=)[^>]*>", html)  # every image has alt text


def test_homepage_uses_live_numbers_only(client, fixture_text):
    ingest("nor", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
    html = client.get("/").text
    assert "Filed this week" in html and "Little Creek" in html and "1214" not in html  # street only
    assert "100 of 100" in html  # founding seats come from the database


def test_llms_txt_robots_and_city_search(client, fixture_text):
    ingest("nor", NORFOLK, json.loads(fixture_text("norfolk_socrata.json")))
    llms = client.get("/llms.txt").text
    assert llms.startswith("# Pegasus") and "/for/roofer" in llms and "$79/mo" in llms
    assert "Allow: /" in client.get("/robots.txt").text
    assert "/leads/va/norfolk" in client.get("/leads?q=norf").text
    assert "/leads/va/norfolk" not in client.get("/leads?q=zzz").text


def test_breadcrumbs_on_seo_pages(client):
    html = client.get("/for/roofer").text
    assert '"BreadcrumbList"' in html and "Roofing Leads" in html


def test_compression_and_cache_headers(client):
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    assert "max-age" in client.get("/static/site.css").headers.get("cache-control", "")
