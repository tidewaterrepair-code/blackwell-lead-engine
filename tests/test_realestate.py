from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from pegasus.db import session_scope, utcnow
from pegasus.models import Listing, MLSConnection, Org, OrgLead, Property
from tests.conftest import ingest, make_org

VB_SALES = {"type": "arcgis", "kind": "sale", "url": "https://h/FeatureServer/1", "city": "Virginia Beach",
            "state": "VA", "county_fips": "51810",
            "fields": {"external_id": "DeedId", "address": "SiteAddress", "sale_price": "Price", "sale_date": "SaleDate",
                       "owner_name": "Owner", "mailing_address": "MailAddr", "sqft": "LivingArea",
                       "year_built": "YearBuilt", "parcel_id": "GPIN"}}
VB_TAX = {"type": "arcgis", "kind": "tax_delinquent", "url": "https://h/FeatureServer/2", "city": "Virginia Beach",
          "state": "VA", "county_fips": "51810",
          "fields": {"external_id": "Acct", "address": "SiteAddress", "amount_due": "Due", "owner_name": "Owner",
                     "parcel_id": "GPIN"}}


def ms(days_ago: int) -> int:
    return int((utcnow() - timedelta(days=days_ago)).timestamp() * 1000)


def sale(i, addr, price, days_ago, lat, lng, sqft=1800, owner="Smith J", mail=None, yb=1975):
    return {"attributes": {"DeedId": f"D{i}", "SiteAddress": addr, "Price": price, "SaleDate": ms(days_ago),
                           "Owner": owner, "MailAddr": mail or addr, "LivingArea": sqft, "YearBuilt": yb,
                           "GPIN": f"G{i}"}, "geometry": {"x": lng, "y": lat}}


def seed_market():
    sales = {"features": [
        sale(1, "100 Ocean Ave", 410000, 30, 36.840, -75.980),
        sale(2, "104 Ocean Ave", 395000, 60, 36.841, -75.981),
        sale(3, "110 Ocean Ave", 420000, 90, 36.842, -75.982),
        sale(4, "120 Ocean Ave", 405000, 120, 36.843, -75.983),
        # Subject: bought 20 years ago, owner lives in another state.
        sale(9, "200 Ocean Ave", 150000, 7300, 36.8405, -75.9805, owner="Doe Estate", mail="55 Pine Rd, Austin TX",
             yb=1960),
    ]}
    ingest("vb-sales", VB_SALES, sales)
    tax = {"features": [{"attributes": {"Acct": "T1", "SiteAddress": "200 Ocean Ave", "Due": "$4,210.55",
                                        "Owner": "Doe Estate", "GPIN": "G9"}, "geometry": {"x": -75.9805, "y": 36.8405}}]}
    ingest("vb-tax", VB_TAX, tax)


def test_distress_stack_motivation_and_sell_probability():
    seed_market()
    with session_scope() as s:
        subject = s.scalar(select(Property).where(Property.parcel_id == "G9"))
        assert subject.absentee is True
        assert "tax_delinquent" in subject.distress
        assert subject.motivation_score >= 50
        neighbor = s.scalar(select(Property).where(Property.parcel_id == "G1"))
        assert subject.sell_probability > neighbor.sell_probability
        assert "Behind on taxes" in subject.data["factors"] and "Owned 15+ years" in subject.data["factors"]
        assert subject.equity_est and subject.equity_est > 0


def test_investor_gets_distressed_lead_and_deal_analysis():
    _, org_id = make_org("inv@x.com", ["investor"], {"kind": "county", "data": {"fips": ["51810"]}})
    seed_market()
    from pegasus.realestate.deals import analyze

    with session_scope() as s:
        leads = s.scalars(select(OrgLead).where(OrgLead.org_id == org_id)).all()
        assert any(l.signal.kind == "tax_delinquent" for l in leads)
        subject = s.scalar(select(Property).where(Property.parcel_id == "G9"))
        result = analyze(s, subject, org_id)
        assert result.arv and 380000 <= result.arv <= 440000
        assert result.mao == round(result.arv * 0.7 - result.repairs, -2)
        assert result.grade in ("A", "B") and len(result.comps) >= 3


def test_skip_trace_charges_credits_flags_dnc_and_refuses_when_empty(monkeypatch):
    seed_market()
    monkeypatch.setenv("BATCHDATA_API_KEY", "x")
    from pegasus.config import get_settings

    get_settings.cache_clear()
    from pegasus.billing import add_credits
    from pegasus.realestate.skiptrace import SkipTraceError, skip_trace

    _, org_id = make_org("agent@x.com", ["real_estate_agent"])
    hit = {"results": {"persons": [{"name": {"first": "Jane", "last": "Doe"},
                                    "phoneNumbers": [{"number": "7575550100", "type": "Mobile", "dnc": True},
                                                     {"number": "7575550101", "type": "Landline"}],
                                    "emails": [{"email": "jane@example.com"}]}]}}
    try:
        with session_scope() as s:
            org = s.get(Org, org_id)
            add_credits(s, org, 3, "test")
            prop = s.scalar(select(Property).where(Property.parcel_id == "G9"))
            client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=hit)))
            contact = skip_trace(s, org, prop=prop, sig=None, client=client)
            assert contact.phones[0]["dnc"] is True and contact.emails == ["jane@example.com"]
            assert org.credits == 2
            again = skip_trace(s, org, prop=prop, sig=None, client=client)  # cached for this org: free
            assert again.id == contact.id and org.credits == 2
            other = s.scalar(select(Property).where(Property.parcel_id == "G1"))
            empty = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {}})))
            with pytest.raises(SkipTraceError):
                skip_trace(s, org, prop=other, sig=None, client=empty)
            assert org.credits == 2
    finally:
        get_settings.cache_clear()


MLS_CSV = b"""MLS #,Status,Address,City,Zip,List Price,Sold Price,SqFt,Close Date,List Date,Status Change Date
A1,Closed,300 Ocean Ave,Virginia Beach,23451,400000,415000,1800,2026-08-01,2026-06-01,2026-08-01
A2,Expired,200 Ocean Ave,Virginia Beach,23451,350000,,1700,,2026-03-01,2026-10-01
"""


def test_mls_csv_import_creates_private_expired_leads():
    seed_market()
    _, agent = make_org("agent@x.com", ["real_estate_agent"], plan="elite")
    _, rival = make_org("rival@x.com", ["real_estate_agent"], plan="elite")
    from pegasus.realestate.mls import import_csv

    with session_scope() as s:
        conn = MLSConnection(org_id=agent, mls_name="REIN", vendor="csv", status="active")
        s.add(conn)
        s.flush()
        result = import_csv(s, conn, MLS_CSV)
        assert result["created"] == 2
    with session_scope() as s:
        expired = s.scalars(select(OrgLead).where(OrgLead.org_id == agent, OrgLead.lead_type == "property")).all()
        assert len(expired) == 1 and "Listing expired" in expired[0].reasons[0]
        assert s.scalars(select(OrgLead).where(OrgLead.org_id == rival, OrgLead.lead_type == "property")).all() == []
        assert s.scalars(select(Listing).where(Listing.org_id == rival)).all() == []


def test_reso_sync_pages_and_handles_errors():
    from pegasus.auth import encrypt_secret
    from pegasus.realestate.mls import sync_connection

    _, agent = make_org("agent@x.com", ["real_estate_agent"], plan="elite")
    with session_scope() as s:
        conn = MLSConnection(org_id=agent, mls_name="Test MLS", vendor="reso", base_url="https://reso.example/odata",
                             token_url="https://reso.example/token", client_id="cid", secret_enc=encrypt_secret("sec"))
        s.add(conn)
        s.flush()
        cid = conn.id
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers["authorization"] == "Bearer tok"
        if "page2" in str(request.url):
            return httpx.Response(200, json={"value": [{"ListingKey": "K2", "StandardStatus": "Withdrawn",
                                                        "UnparsedAddress": "9 Bay St", "City": "Norfolk"}]})
        return httpx.Response(200, json={"value": [{"ListingKey": "K1", "StandardStatus": "Active",
                                                    "UnparsedAddress": "8 Bay St", "ListPrice": 300000}],
                                         "@odata.nextLink": "https://reso.example/odata/Property?page2"})

    out = sync_connection(cid, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert out == {"created": 2, "updated": 0, "status": "active"}
    bad = sync_connection(cid, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    assert bad["status"] == "error"


def test_farm_stats():
    seed_market()
    from pegasus.accounts import create_territory
    from pegasus.realestate.farm import farm_stats

    _, agent = make_org("agent@x.com", ["real_estate_agent"])
    with session_scope() as s:
        terr = create_territory(s, s.get(Org, agent), kind="radius", data={"lat": 36.84, "lng": -75.98, "miles": 2})
        stats = farm_stats(s, terr, agent)
    assert stats["sales_12mo"] == 4 and stats["median_sale_price"] == 407500
    assert stats["hottest_streets"][0]["street"] == "Ocean Ave"


def test_shared_scores_ignore_private_records():
    from pegasus.ingest import upsert_signal
    from pegasus.realestate.properties import refresh_property
    from pegasus.sources.base import LeadInput

    with session_scope() as s:
        sig, _ = upsert_signal(s, "manual:1", LeadInput(external_id="m", kind="manual", title="Fire damage repair",
                                                         address="77 Elm St", city="Norfolk", state="VA"))
        refresh_property(s, sig.property)
        assert sig.property.motivation_score == 0
