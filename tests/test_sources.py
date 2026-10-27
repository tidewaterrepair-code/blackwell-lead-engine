import json
from datetime import datetime, timedelta

import httpx

from pegasus.db import utcnow
from pegasus.sources import build_adapter
from pegasus.sources.accela import AccelaAdapter, parse_aca_results
from pegasus.sources.agendas import development_items
from pegasus.sources.inbox import IMAPAdapter, parse_message


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


def test_arcgis_text_date_field():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"features": [{"attributes": {
            "PermitNumber": "2026-BLDR-1", "WorkDesc": "New deck", "ApplicationDate": "2026/10/23"}}]})

    cfg = {"type": "arcgis", "url": "https://services2.arcgis.com/x/FeatureServer/0", "city": "Virginia Beach",
           "date_field": "ApplicationDate", "date_format": "%Y/%m/%d",
           "fields": {"external_id": "PermitNumber", "description": "WorkDesc", "posted_at": "ApplicationDate"}}
    adapter = build_adapter("vb", cfg, client=mock_client(handler))
    items = list(adapter.fetch(datetime(2026, 10, 1)))
    assert calls[0].params["where"] == "ApplicationDate >= '2026/10/01'"
    assert adapter.normalize(items[0].payload).posted_at == datetime(2026, 10, 23)


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
    # the fixture was captured on 2026-10-04; shift its dates so "recent" and "still open" hold on any run date
    shift = (utcnow().date() - datetime(2026, 10, 4).date()).days
    body = fixture_bytes("bids.rss").decode()
    for old, fmt in (("Sun, 04 Oct 2026", "%a, %d %b %Y"), ("October 18, 2026", "%B %d, %Y"), ("10/11/2026", "%m/%d/%Y")):
        body = body.replace(old, (datetime.strptime(old, fmt) + timedelta(days=shift)).strftime(fmt))

    def handler(request):
        return httpx.Response(200, content=body.encode(),
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


def test_noaa_storm_reports(fixture_text):
    def handler(request):
        if "hail" in str(request.url) and "today" in str(request.url):
            return httpx.Response(200, text=fixture_text("spc_hail.csv"))
        return httpx.Response(404)

    adapter = build_adapter("noaa", {"type": "noaa_storms", "kind": "storm", "days": ["today"]},
                            client=httpx.Client(transport=httpx.MockTransport(handler)))
    items = [adapter.normalize(r.payload) for r in adapter.fetch(utcnow())]
    kept = [i for i in items if i]
    assert len(items) == 2 and len(kept) == 1  # penny-size hail filtered out
    assert kept[0].title.startswith("Hail 1.75 in") and kept[0].radius_miles == 5.0 and kept[0].kind == "storm"


def test_csv_and_excel_tax_lists():
    import io

    from openpyxl import Workbook

    from pegasus.sources.tabular import read_table

    csv_rows = read_table(b"GPIN,Property Address,Amount Due\n123,5 Elm St,\"$1,200.00\"\n")
    assert csv_rows == [{"GPIN": "123", "Property Address": "5 Elm St", "Amount Due": "$1,200.00"}]
    wb = Workbook()
    ws = wb.active
    ws.append(["Delinquent list as of Oct 1"])
    ws.append(["GPIN", "Property Address", "Amount Due"])
    ws.append(["456", "9 Oak St", 845.5])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    rows = read_table(content, url="list.xlsx", skip_rows=1)
    assert rows == [{"GPIN": "456", "Property Address": "9 Oak St", "Amount Due": 845.5}]
    adapter = build_adapter("tax", {"type": "csv", "kind": "tax_delinquent", "url": "https://x/list.xlsx",
                                    "skip_rows": 1, "city": "Norfolk",
                                    "fields": {"address": "Property Address", "amount_due": "Amount Due",
                                               "parcel_id": "GPIN"}},
                            client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content))))
    item = adapter.normalize(next(iter(adapter.fetch(utcnow()))).payload)
    assert item.kind == "tax_delinquent" and item.address == "9 Oak St" and item.facts["amount_due"] == 845.5


def _robots_client(robots_status: int, robots_body: str = ""):
    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(robots_status, text=robots_body)
        return httpx.Response(200, text="<html><body>ok</body></html>")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_robots_txt_rules():
    import pytest as _pytest

    from pegasus.sources import base
    from pegasus.sources.feeds import HTMLListAdapter

    base._ROBOTS.clear()
    assert base.robots_allowed("https://a.test/permits", _robots_client(404))  # no robots.txt: allowed
    base._ROBOTS.clear()
    assert not base.robots_allowed("https://b.test/permits", _robots_client(503))  # server error: back off
    base._ROBOTS.clear()
    blocked = _robots_client(200, "User-agent: PegasusLeadBot\nDisallow: /permits\n")
    assert not base.robots_allowed("https://c.test/permits/list", blocked)
    assert base.robots_allowed("https://c.test/news", blocked)
    base._ROBOTS.clear()
    adapter = HTMLListAdapter("t", {"type": "html_list", "url": "https://d.test/bids", "item": "li"},
                              client=_robots_client(200, "User-agent: *\nDisallow: /\n"))
    with _pytest.raises(base.RobotsDisallowed):
        list(adapter.fetch(datetime(2026, 1, 1)))
    base._ROBOTS.clear()


def test_env_ignores_inline_comment_values(monkeypatch):
    from pegasus.config import _env

    monkeypatch.setenv("SOCRATA_APP_TOKEN", "# free; raises open-data rate limits")
    assert _env("SOCRATA_APP_TOKEN") is None
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "  abc123  ")
    assert _env("SOCRATA_APP_TOKEN") == "abc123"
