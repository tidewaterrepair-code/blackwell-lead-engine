import json
from datetime import timedelta

from sqlalchemy import func, select

from pegasus.db import session_scope, utcnow
from pegasus.models import OrgLead, Prediction, Property, RawRecord, Signal, Source
from tests.conftest import HAMPTON_ROADS, NORFOLK, VB, VB_NORFOLK_COUNTIES, add_source, ingest, make_org


def leads_for(org_id):
    with session_scope() as s:
        return [(l.lead_type, l.trade, l.signal.primary_tag, l.prediction.tag if l.prediction else None)
                for l in s.scalars(select(OrgLead).where(OrgLead.org_id == org_id))]


def test_signals_are_shared_and_runs_are_idempotent(fixture_text):
    rows = json.loads(fixture_text("norfolk_socrata.json"))
    res = ingest("norfolk-permits", NORFOLK, rows)
    assert res.error is None and res.fetched == 5
    assert res.new_signals == 4  # void permit dropped; the electrical permit is kept for electricians
    again = ingest("norfolk-permits", NORFOLK, rows)
    assert again.new_signals == 0 and again.updated_signals == 4
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Signal)) == 4
        assert s.scalar(select(func.count()).select_from(RawRecord)) == 5
        home = s.scalar(select(Signal).where(Signal.external_id == "B2026-10011"))
        assert home.primary_tag == "new_construction" and home.county_fips == "51710"
        assert home.property_id is not None
        assert s.scalar(select(func.count()).select_from(Prediction).where(Prediction.signal_id == home.id)) > 10
        assert s.get(Source, "norfolk-permits").last_status == "ok"


def test_fan_out_respects_trades_and_territories(norfolk_vb):
    _, framer = make_org("framer@x.com", ["framer"], VB_NORFOLK_COUNTIES)
    _, roofer = make_org("roofer@x.com", ["roofer"], VB_NORFOLK_COUNTIES)
    _, electrician = make_org("sparky@x.com", ["electrician"], VB_NORFOLK_COUNTIES)
    _, far_away = make_org("richmond@x.com", ["framer"], {"kind": "county", "data": {"fips": ["51760"]}})
    norfolk_vb()
    framer_leads = leads_for(framer)
    assert ("signal", "framer", "new_construction", None) in framer_leads
    assert all(t != "roofing" for _, _, t, _ in framer_leads)
    roofer_leads = leads_for(roofer)
    assert ("signal", "roofer", "roofing", None) in roofer_leads  # the VB reroof permit
    assert any(lt == "prediction" and pt == "roofing" for lt, _, _, pt in roofer_leads)  # new homes need roofs
    assert ("signal", "electrician", "electrical", None) in leads_for(electrician)
    assert leads_for(far_away) == []


def test_new_org_gets_backfilled_with_recent_signals(norfolk_vb):
    norfolk_vb()
    _, org = make_org("late@x.com", ["deck_builder"], VB_NORFOLK_COUNTIES)
    from pegasus.jobs import drain
    from pegasus import tasks  # noqa: F401 - registers handlers

    drain()
    assert any(tag == "deck" for _, _, tag, _ in leads_for(org))


def test_exclusive_zip_blocks_other_orgs(fixture_text):
    from pegasus.accounts import create_territory
    from pegasus.models import Org

    _, owner = make_org("owner@x.com", ["deck_builder"], plan="team")
    _, other = make_org("other@x.com", ["deck_builder"], {"kind": "zip", "data": {"zips": ["23456", "23454"]}})
    with session_scope() as s:
        create_territory(s, s.get(Org, owner), kind="zip", data={"zips": ["23456"]}, exclusive=True)
    rows = {"features": [{"attributes": {"PermitNumber": "D-1", "WorkDesc": "Build new deck", "FullAddress":
                                         "12 Ocean Ave, Virginia Beach VA 23456", "ApplicationDate": 1790000000000}},
                         {"attributes": {"PermitNumber": "D-2", "WorkDesc": "Build new deck", "FullAddress":
                                         "9 Bay St, Virginia Beach VA 23454", "ApplicationDate": 1790000000000}}]}
    ingest("vb", VB, rows)
    owner_ext = {l for l in leads_for(owner)}
    with session_scope() as s:
        other_signals = {l.signal.external_id for l in s.scalars(select(OrgLead).where(OrgLead.org_id == other))}
        owner_signals = {l.signal.external_id for l in s.scalars(select(OrgLead).where(OrgLead.org_id == owner))}
    assert owner_signals == {"D-1"} and owner_ext
    assert other_signals == {"D-2"}  # 23456 is exclusive to the owner


def test_free_plan_is_delayed_and_capped(fixture_text):
    from pegasus.models import Org

    _, org = make_org("free@x.com", ["framer", "deck_builder"], plan="free")
    with session_scope() as s:
        o = s.get(Org, org)
        from pegasus.accounts import create_territory

        create_territory(s, o, kind="zip", data={"zips": ["23456"]})
    rows = {"features": [{"attributes": {"PermitNumber": f"N-{i}", "WorkDesc": "New single family dwelling",
                                         "FullAddress": f"{i} Main St, Virginia Beach VA 23456",
                                         "ApplicationDate": 1790000000000}} for i in range(1, 20)]}
    ingest("vb", VB, rows)
    with session_scope() as s:
        leads = s.scalars(select(OrgLead).where(OrgLead.org_id == org)).all()
        assert len(leads) == 15  # monthly cap
        assert all(l.visible_at > utcnow() + timedelta(days=6) for l in leads)  # 7-day delay


def test_private_manual_signals_never_fan_out():
    from pegasus.ingest import fan_out_signals, upsert_signal
    from pegasus.sources.base import LeadInput

    _, other = make_org("other@x.com", ["deck_builder"], VB_NORFOLK_COUNTIES)
    with session_scope() as s:
        sig, _ = upsert_signal(s, "manual:999", LeadInput(external_id="m1", kind="manual", title="Deck for my neighbor",
                                                           address="5 Pine St", city="Norfolk", state="VA"))
        fan_out_signals(s, [sig.id])
    assert leads_for(other) == []


def test_cross_source_duplicates_link_and_property_is_shared():
    a = [{"permit_number": "N-1", "address": "100 Oak Street", "type": "Building", "work_description": "build deck",
          "issue_date": "2026-10-01"}]
    b = {"features": [{"attributes": {"PermitNumber": "V-9", "WorkDesc": "Deck at rear", "FullAddress": "100 Oak St",
                                      "ApplicationDate": 1790000000000}}]}
    ingest("a", NORFOLK, a)
    ingest("b", VB, b)
    with session_scope() as s:
        first = s.scalar(select(Signal).where(Signal.external_id == "N-1"))
        second = s.scalar(select(Signal).where(Signal.external_id == "V-9"))
        assert second.duplicate_of_id == first.id
        assert s.scalar(select(func.count()).select_from(Property)) >= 1


def test_broken_source_is_recorded_and_eventually_marked_broken():
    import httpx

    from pegasus.ingest import run_source

    add_source("down", NORFOLK)
    for _ in range(5):
        res = run_source("down", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
        assert res.error and "503" in res.error
    with session_scope() as s:
        src = s.get(Source, "down")
        assert src.last_status == "error" and src.status == "broken"

    res = run_source("down", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))))
    assert res.error is None
    with session_scope() as s:
        assert s.get(Source, "down").status == "active"


def test_storm_signal_reaches_roofers_in_the_area():
    _, roofer = make_org("roof@x.com", ["roofer"], HAMPTON_ROADS)
    from pegasus.ingest import fan_out_signals, make_predictions, upsert_signal
    from pegasus.sources.base import LeadInput

    with session_scope() as s:
        sig, _ = upsert_signal(s, "noaa", LeadInput(external_id="hail-1", kind="storm",
                                                     title="Hail 1.75 in near Virginia Beach", lat=36.84, lng=-76.05,
                                                     radius_miles=5, posted_at=utcnow(), state="VA"))
        make_predictions(s, sig)
        fan_out_signals(s, [sig.id])
    assert any(lt == "prediction" and pt == "roofing" for lt, _, _, pt in leads_for(roofer))
