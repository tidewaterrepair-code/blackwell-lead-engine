"""Farm-area analytics and the branded monthly market report for agents."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..geo import Located, territory_contains
from ..models import Listing, Property, Signal, Territory


def _in_territory(terr: Territory, lat, lng, zip_code, fips, city, state) -> bool:
    return territory_contains(terr.kind, terr.data, Located(lat, lng, zip_code, fips, city, state))


def _street(address: str | None) -> str | None:
    if not address:
        return None
    parts = address.split(",")[0].split()
    return " ".join(parts[1:]).title() if len(parts) > 1 and parts[0][0].isdigit() else None


def farm_stats(session: Session, terr: Territory, org_id: int) -> dict:
    now = utcnow()
    year_ago = now - timedelta(days=365)
    stmt = select(Signal).where(Signal.created_at >= now - timedelta(days=730), ~Signal.source_id.like("manual:%"),
                                ~Signal.source_id.like("mls:%"))
    if terr.min_lat is not None:
        stmt = stmt.where(Signal.lat.between(terr.min_lat, terr.max_lat), Signal.lng.between(terr.min_lng, terr.max_lng))
    elif terr.kind == "zip":
        stmt = stmt.where(Signal.zip.in_(terr.data.get("zips", [])))
    elif terr.kind == "county":
        stmt = stmt.where(Signal.county_fips.in_(terr.data.get("fips", [])))
    signals = [s for s in session.scalars(stmt.limit(20000))
               if _in_territory(terr, s.lat, s.lng, s.zip, s.county_fips, s.city, s.state)]
    sales = [s for s in signals if s.kind == "sale" and (s.posted_at or s.created_at) >= year_ago]
    prices = [s.est_value for s in sales if s.est_value and s.est_value > 10_000]
    prop_ids = {s.property_id for s in signals if s.property_id}
    props = session.scalars(select(Property).where(Property.id.in_(prop_ids))).all() if prop_ids else []
    absentee = sum(1 for p in props if p.absentee)
    distressed = sum(1 for p in props if p.motivation_score >= 40)
    streets = Counter(_street(s.address) for s in signals if _street(s.address))
    listings = session.scalars(select(Listing).where(Listing.org_id == org_id)).all()
    listings = [l for l in listings if _in_territory(terr, l.lat, l.lng, l.zip, None, l.city, None)]
    closed = [l for l in listings if l.status == "Closed" and l.close_date and l.close_date >= year_ago]
    active = [l for l in listings if l.status == "Active"]
    dom = [l.days_on_market for l in closed if l.days_on_market]
    return {
        "territory": {"id": terr.id, "name": terr.name},
        "properties_tracked": len(props),
        "sales_12mo": len(sales),
        "turnover_rate": round(len(sales) / len(props), 3) if props else None,
        "median_sale_price": statistics.median(prices) if prices else None,
        "absentee_share": round(absentee / len(props), 3) if props else None,
        "motivated_owners": distressed,
        "permits_12mo": sum(1 for s in signals if s.kind == "permit" and (s.posted_at or s.created_at) >= year_ago),
        "hottest_streets": [{"street": st, "activity": n} for st, n in streets.most_common(8)],
        "mls": {
            "active": len(active), "closed_12mo": len(closed),
            "median_close_price": statistics.median([l.close_price for l in closed if l.close_price]) if closed else None,
            "median_dom": statistics.median(dom) if dom else None,
            "expired_withdrawn_90d": sum(1 for l in listings if l.status in ("Expired", "Withdrawn", "Canceled")
                                         and l.status_changed_at and l.status_changed_at >= now - timedelta(days=90)),
        },
        "as_of": now.date().isoformat(),
    }
