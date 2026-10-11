"""Demo data: realistic Hampton Roads permits, sales, distress records and storms + demo accounts.

    pegasus demo            # seed into the configured database
Use on a fresh/dev database only.
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from .accounts import award, create_territory, signup
from .db import session_scope, utcnow
from .ingest import fan_out_signals, make_predictions, upsert_signal
from .models import Org, OrgLead, Source, User
from .sources.base import LeadInput

STREETS = ["Shore Dr", "Great Neck Rd", "Laskin Rd", "Kempsville Rd", "Princess Anne Rd", "Battlefield Blvd",
           "Colley Ave", "Granby St", "Little Creek Rd", "Indian River Rd", "Holland Rd", "Lynnhaven Pkwy",
           "Hampton Blvd", "Military Hwy", "Cedar Rd", "Volvo Pkwy", "Atlantic Ave", "Pacific Ave"]
PLACES = [("Virginia Beach", "51810", "23451", 36.85, -76.03), ("Virginia Beach", "51810", "23456", 36.76, -76.06),
          ("Norfolk", "51710", "23505", 36.90, -76.27), ("Norfolk", "51710", "23508", 36.88, -76.30),
          ("Chesapeake", "51550", "23322", 36.68, -76.24), ("Chesapeake", "51550", "23320", 36.75, -76.22)]
PERMITS = [
    ("New single family dwelling, 2 story, attached garage", 285000, 520000),
    ("Construct 16x20 composite deck with stairs", 12000, 32000),
    ("Screened porch addition over existing patio", 18000, 45000),
    ("Second story addition, 650 sq ft", 120000, 240000),
    ("Kitchen remodel, remove load bearing wall, new LVL beam", 45000, 110000),
    ("Primary bathroom remodel, curbless shower, new vanity", 18000, 48000),
    ("Construct 24x30 detached garage with loft", 48000, 95000),
    ("Reroof, architectural shingles, replace decking as needed", 11000, 26000),
    ("HVAC changeout, 3 ton heat pump", 8000, 14000),
    ("200A electrical service upgrade and EV charger", 3500, 9000),
    ("Install 9.6 kW rooftop solar PV system", 22000, 38000),
    ("In-ground swimming pool with paver deck", 55000, 110000),
    ("6 ft vinyl privacy fence, 180 LF", 6000, 14000),
    ("Replace 60 ft bulkhead and install boat lift", 45000, 120000),
    ("Interior renovation after water damage, drywall and flooring", 25000, 70000),
    ("Demolition of single family dwelling", 15000, 30000),
]


def _addr(rng: random.Random) -> str:
    return f"{rng.randint(100, 5999)} {rng.choice(STREETS)}"


def seed(days: int = 21, n_permits: int = 140, rng_seed: int = 7) -> dict:
    rng = random.Random(rng_seed)
    now = utcnow()
    with session_scope() as s:
        for sid, kind in (("demo-permits", "permit"), ("demo-sales", "sale"), ("demo-tax", "tax_delinquent"),
                          ("demo-foreclosures", "foreclosure"), ("demo-storms", "storm"), ("demo-bids", "bid")):
            if s.get(Source, sid) is None:
                s.add(Source(id=sid, name=f"Demo {kind}", type="csv", kind=kind, config={}, status="disabled",
                             origin="admin"))

    def make(s, sid, item):
        sig, created = upsert_signal(s, sid, item)
        if sig is not None:
            make_predictions(s, sig)
        return sig

    ids = []
    with session_scope() as s:
        for i in range(n_permits):
            desc, lo, hi = rng.choice(PERMITS)
            city, fips, zip_code, lat, lng = rng.choice(PLACES)
            posted = now - timedelta(days=rng.random() ** 1.6 * days, hours=rng.randint(0, 20))
            item = LeadInput(external_id=f"P-{i}", kind="permit", title=f"Building · {desc.split(',')[0]}",
                             description=desc, address=_addr(rng), city=city, state="VA", zip=zip_code,
                             county_fips=fips, lat=lat + rng.uniform(-0.05, 0.05), lng=lng + rng.uniform(-0.05, 0.05),
                             est_value=round(rng.uniform(lo, hi), -2), posted_at=posted,
                             contractor_name=rng.choice([None, None, "Owner", "Tidewater Custom Homes", "Coastal Builders LLC",
                                                         "Bayside Remodeling", "Atlantic Framing Co"]))
            sig = make(s, "demo-permits", item)
            if sig:
                ids.append(sig.id)
        # Sales (comps + new owners), tax delinquencies and pre-foreclosures for real estate users
        for i in range(60):
            city, fips, zip_code, lat, lng = rng.choice(PLACES)
            sold = now - timedelta(days=rng.randint(1, 330))
            yb = rng.randint(1950, 2018)
            item = LeadInput(external_id=f"S-{i}", kind="sale", title="Sold", address=_addr(rng), city=city, state="VA",
                             zip=zip_code, county_fips=fips, lat=lat + rng.uniform(-0.03, 0.03),
                             lng=lng + rng.uniform(-0.03, 0.03), est_value=round(rng.uniform(240000, 680000), -3),
                             posted_at=sold, owner_name=f"Owner {i}",
                             facts={"sale_date": sold.isoformat(), "sqft": rng.randint(1200, 3400), "year_built": yb,
                                    "parcel_id": f"DEMO-S{i}"})
            sig = make(s, "demo-sales", item)
            if sig:
                ids.append(sig.id)
        for i in range(25):
            city, fips, zip_code, lat, lng = rng.choice(PLACES)
            kind = rng.choice(["tax_delinquent", "tax_delinquent", "foreclosure", "violation", "probate"])
            bought = now - timedelta(days=rng.randint(15 * 365, 34 * 365))
            item = LeadInput(external_id=f"D-{i}", kind=kind, title={"tax_delinquent": "Delinquent real estate taxes",
                                                                     "foreclosure": "Trustee sale notice",
                                                                     "violation": "Code violation: deteriorated deck and roof",
                                                                     "probate": "Estate filed in circuit court"}[kind],
                             address=_addr(rng), city=city, state="VA", zip=zip_code, county_fips=fips,
                             lat=lat + rng.uniform(-0.04, 0.04), lng=lng + rng.uniform(-0.04, 0.04),
                             posted_at=now - timedelta(days=rng.randint(1, 40)), owner_name=f"Estate of Owner {i}",
                             facts={"parcel_id": f"DEMO-D{i}", "year_built": rng.randint(1945, 1985),
                                    "sqft": rng.randint(1100, 2600), "mailing_address": rng.choice(
                                        ["12 Elm St, Raleigh NC", "450 Pine Ave, Columbus OH", None]),
                                    "amount_due": round(rng.uniform(1800, 14000), 2)})
            sig = make(s, f"demo-{'tax' if kind == 'tax_delinquent' else 'foreclosures'}", item)
            if sig:
                ids.append(sig.id)
            # An old sale on the same address so equity and ownership length are known
            make(s, "demo-sales", LeadInput(external_id=f"SO-{i}", kind="sale", title="Sold", address=item.address,
                                            city=city, state="VA", zip=zip_code, county_fips=fips, lat=item.lat,
                                            lng=item.lng, est_value=round(rng.uniform(60000, 160000), -3),
                                            posted_at=bought, facts={"sale_date": bought.isoformat(),
                                                                     "parcel_id": f"DEMO-D{i}"}))
        storm = make(s, "demo-storms", LeadInput(external_id="H-1", kind="storm", title="Hail 1.75 in near Kempsville, VA",
                                                 lat=36.83, lng=-76.15, radius_miles=6, state="VA", city="Virginia Beach",
                                                 posted_at=now - timedelta(hours=20)))
        ids.append(storm.id)
        bid = make(s, "demo-bids", LeadInput(external_id="B-1", kind="bid", title="IFB 26-114 Fire Station 9 kitchen and restroom renovation",
                                             city="Norfolk", state="VA", county_fips="51710",
                                             posted_at=now - timedelta(days=2), due_at=now + timedelta(days=12),
                                             url="https://www.norfolk.gov/bids"))
        ids.append(bid.id)
        from .realestate.properties import refresh_scores

        refresh_scores(s, ids)

    with session_scope() as s:
        accounts = {}
        for email, name, org_name, trades, plan, terr in (
            ("demo@pegasus.test", "Dee Walker", "Walker Decks & Framing", ["deck_builder", "framer", "roofer"], "growth",
             {"kind": "radius", "data": {"lat": 36.82, "lng": -76.12, "miles": 30, "label": "Virginia Beach"}}),
            ("agent@pegasus.test", "Ava Brooks", "Brooks Realty Group", ["real_estate_agent", "investor"], "elite",
             {"kind": "county", "data": {"fips": ["51810", "51710", "51550"]}}),
        ):
            user = s.scalar(select(User).where(User.email == email))
            if user is None:
                user, org = signup(s, email=email, password="pegasus-demo", name=name, org_name=org_name, trades=trades)
                org.plan, org.plan_status = plan, "active"
                org.settings = {**org.settings, "onboarded": True, "monthly_goal": 60000}
                org.credits = 40
                create_territory(s, org, **terr)
                user.streak_days, user.last_active_on = 6, (now - timedelta(days=1)).date().isoformat()
                for action in ("lead_contacted", "lead_quoted", "lead_won"):
                    award(s, user, org.id, action)
            accounts[email] = user.id
        boss = s.scalar(select(User).where(User.email == "boss@pegasus.test"))
        if boss is None:
            boss, org = signup(s, email="boss@pegasus.test", password="pegasus-demo", name="Founder", org_name="Pegasus HQ",
                               trades=["general_contractor"])
            boss.is_admin = True
            org.settings = {**org.settings, "onboarded": True}
    with session_scope() as s:
        created = fan_out_signals(s, ids)
        # Put a few leads into the demo pipeline so the board isn't empty.
        org = s.scalar(select(Org).where(Org.name == "Walker Decks & Framing"))
        leads = s.scalars(select(OrgLead).where(OrgLead.org_id == org.id, OrgLead.lead_type == "signal")
                          .order_by(OrgLead.score.desc())).all()
        for lead, status in zip(leads[6:14], ["saved", "saved", "contacted", "contacted", "quoted", "quoted", "won", "lost"]):
            lead.status = status
            if status == "won":
                lead.value_won = 26500
    return {"signals": len(ids), "org_leads": created, "accounts": ["demo@pegasus.test", "agent@pegasus.test",
                                                                    "boss@pegasus.test (admin)"], "password": "pegasus-demo"}
