import json
from datetime import timedelta

import httpx

from leadengine.db import utcnow
from leadengine.sources import build_adapter
from leadengine.sources.accela import AccelaAdapter, parse_aca_results
from leadengine.sources.agendas import development_items
from leadengine.sources.inbox import IMAPAdapter, parse_message


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_socrata_fetch_and_normalize(fixture_text):
    rows = json.loads(fixture_text("norfolk_socrata.json"))
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=rows)

    cfg = {"type": "socrata", "domain": "data.norfolk.gov", "dataset": "fahm-yuh4", "city": "Norfolk"}
    adapter = build_adapter("norfolk", cfg, client=mock_client(handler))
    items = list(adapter.fetch(utcnow() - timedelta(days=7)))
    assert "data.norfolk.gov/resource/fahm-yuh4.json" in seen["url"]
    assert "%3Aupdated_at" in seen["url"] or ":updated_at" in seen["url"]
    assert [i.external_id for i in items][:2] == ["B2026-10011", "B2026-10012"]

    lead = adapter.normalize(items[0].payload)
    assert lead.address == "1214 W Little Creek Rd"
    assert lead.city == "Norfolk"
    assert lead.est_value == 385000
    assert lead.contractor_name == "Tidewater Custom Homes LLC"
    assert lead.lat and lead.lng
    assert "Single Family Dwelling" in lead.hints
    # void permits are skipped
    assert adapter.normalize(rows[4]) is None


def test_arcgis_fetch_and_normalize(fixture_text):
    data = json.loads(fixture_text("vb_arcgis.json"))
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json=data)

    cfg = {"type": "arcgis", "url": "https://services2.arcgis.com/x/FeatureServer/0", "city": "Virginia Beach",
           "date_field": "ApplicationDate", "fields": {"external_id": "PermitNumber", "description": "WorkDesc"}}
    adapter = build_adapter("vb", cfg, client=mock_client(handler))
    items = list(adapter.fetch(utcnow() - timedelta(days=7)))
    assert len(items) == 5 and len(calls) == 1
    assert "ApplicationDate" in calls[0].params["where"]
    lead = adapter.normalize(items[0].payload)
    assert lead.external_id == "BLDR-2026-0501"
    assert "deck" in lead.description
    assert lead.address == "2417 Haversham Close"
    assert round(lead.lat, 3) == 36.841 and round(lead.lng, 3) == -76.060
    assert lead.posted_at is not None


def test_accela_results_parsing(fixture_text):
    rows = parse_aca_results(fixture_text("aca_results.html"), "https://aca-prod.accela.com/CHESAPEAKE")
    assert len(rows) == 2
    adapter = AccelaAdapter("ches", {"type": "accela", "base_url": "https://aca-prod.accela.com/CHESAPEAKE",
                                     "city": "Chesapeake"})
    lead = adapter.normalize(rows[0])
    assert lead.external_id == "BLD-RES-2026-01234"
    assert lead.description.startswith("Sunroom addition")
    assert lead.url.startswith("https://aca-prod.accela.com/CHESAPEAKE/Cap/CapDetail.aspx")
    assert lead.posted_at.month == 9


def test_rss_bids(fixture_bytes):
    def handler(request):
        return httpx.Response(200, content=fixture_bytes("bids.rss"),
                              headers={"content-type": "application/rss+xml"})

    adapter = build_adapter("bids", {"type": "rss", "kind": "bid", "url": "https://x/rss", "city": "Norfolk"},
                            client=mock_client(handler))
    items = list(adapter.fetch(utcnow() - timedelta(days=30)))
    assert len(items) == 3
    lead = adapter.normalize(items[0].payload)
    assert lead.kind == "bid"
    assert lead.due_at is not None and lead.due_at > utcnow()
    assert lead.url.endswith("bidID=114")


def test_html_list_adapter():
    page = """<table class="bids"><tr><td>Bid 1</td><td><a href="/b/1">Deck repairs at Lake Smith park</a></td><td>10/30/2026</td></tr>
              <tr><td>Bid 2</td><td><a href="/b/2">Mowing</a></td><td>11/01/2026</td></tr></table>"""

    def handler(request):
        return httpx.Response(200, text=page)

    cfg = {"type": "html_list", "kind": "bid", "url": "https://city.gov/bids", "item": "table.bids tr",
           "title": "td:nth-child(2)", "due": "td:nth-child(3)"}
    adapter = build_adapter("h", cfg, client=mock_client(handler))
    items = list(adapter.fetch(utcnow()))
    assert [i.payload["link"] for i in items] == ["https://city.gov/b/1", "https://city.gov/b/2"]
    lead = adapter.normalize(items[0].payload)
    assert lead.due_at.year == 2026 and lead.due_at.month == 10


def test_agenda_items(fixture_text):
    items = development_items(fixture_text("agenda.txt"))
    assert len(items) == 2
    assert "48 single-family residential lots" in items[0]
    assert "31 townhomes" in items[1]


def test_email_request(fixture_bytes):
    payload = parse_message(fixture_bytes("craigslist_alert.eml"))
    adapter = IMAPAdapter("mail", {"type": "imap", "kind": "request"})
    lead = adapter.normalize(payload)
    assert lead.kind == "request"
    assert lead.phone == "(757) 555-0142"
    assert lead.email == "mike.h@example.com"
    assert lead.city == "Chesapeake"
    assert "deck" in lead.description
