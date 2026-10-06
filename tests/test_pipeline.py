import json

import httpx
from sqlalchemy import func, select

from leadengine.db import Lead, RawRecord, Source, session_scope
from leadengine.pipeline import add_manual_lead, run_source


def _client(payload):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


NORFOLK = {"type": "socrata", "kind": "permit", "domain": "data.norfolk.gov", "dataset": "x", "city": "Norfolk"}
VB = {"type": "arcgis", "kind": "permit", "url": "https://h/FeatureServer/0", "city": "Virginia Beach",
      "date_field": "ApplicationDate", "fields": {"external_id": "PermitNumber", "description": "WorkDesc"}}


def test_run_is_idempotent_and_filters_noise(fixture_text):
    rows = json.loads(fixture_text("norfolk_socrata.json"))
    res = run_source("norfolk-permits", NORFOLK, client=_client(rows))
    assert res.error is None
    assert res.fetched == 5
    assert res.new_leads == 3  # new home, deck, kitchen; electrical + void dropped

    again = run_source("norfolk-permits", NORFOLK, client=_client(rows))
    assert again.new_leads == 0 and again.updated_leads == 3

    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Lead)) == 3
        assert s.scalar(select(func.count()).select_from(RawRecord)) == 5
        src = s.get(Source, "norfolk-permits")
        assert src.last_status == "ok" and src.last_success_at is not None
        home = s.scalar(select(Lead).where(Lead.external_id == "B2026-10011"))
        assert home.job_type == "new_construction" and home.customer_type == "builder"
        deck = s.scalar(select(Lead).where(Lead.external_id == "B2026-10012"))
        assert deck.job_type == "deck" and deck.customer_type == "homeowner"
        assert home.score > 0 and deck.score > 0


def test_user_edits_survive_reingest(fixture_text):
    rows = json.loads(fixture_text("norfolk_socrata.json"))
    run_source("norfolk-permits", NORFOLK, client=_client(rows))
    with session_scope() as s:
        deck = s.scalar(select(Lead).where(Lead.external_id == "B2026-10012"))
        deck.status, deck.phone, deck.job_type, deck.classified_by = "contacted", "757-555-0100", "addition", "manual"
    run_source("norfolk-permits", NORFOLK, client=_client(rows))
    with session_scope() as s:
        deck = s.scalar(select(Lead).where(Lead.external_id == "B2026-10012"))
        assert (deck.status, deck.phone, deck.job_type) == ("contacted", "757-555-0100", "addition")


def test_cross_source_duplicates_are_linked():
    a = [{"permit_number": "N-1", "address": "100 Oak Street", "type": "Building",
          "work_description": "build deck", "issue_date": "2026-10-01"}]
    b = {"features": [{"attributes": {"PermitNumber": "V-9", "WorkDesc": "Deck at rear",
                                      "FullAddress": "100 Oak St", "ApplicationDate": 1790000000000}}]}
    run_source("a", NORFOLK, client=_client(a))
    run_source("b", VB, client=_client(b))
    with session_scope() as s:
        first = s.scalar(select(Lead).where(Lead.external_id == "N-1"))
        second = s.scalar(select(Lead).where(Lead.external_id == "V-9"))
        assert second.duplicate_of_id == first.id


def test_broken_source_is_recorded_not_raised():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    res = run_source("down", NORFOLK, client=client)
    assert res.error and "503" in res.error
    with session_scope() as s:
        assert s.get(Source, "down").last_status == "error"


def test_manual_lead():
    with session_scope() as s:
        lead = add_manual_lead(s, {"title": "Neighbor wants 16x20 deck", "phone": "757-555-0199",
                                   "city": "Chesapeake", "est_value": "18000"})
        assert lead.job_type == "deck" and lead.score > 0
        other = add_manual_lead(s, {"title": "Call back Joe about something"})
        assert other.id and other.job_type == "other"


def test_unsafe_links_are_dropped():
    with session_scope() as s:
        lead = add_manual_lead(s, {"title": "Deck job", "url": "javascript:alert(1)"})
        assert lead.url is None
        ok = add_manual_lead(s, {"title": "Deck job 2", "url": "https://example.com/post"})
        assert ok.url == "https://example.com/post"
