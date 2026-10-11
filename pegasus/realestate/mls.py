"""MLS connect: RESO Web API sync (OAuth2) and CSV import. Listing data stays private to the org.

Agents/brokers request a data feed from their MLS's licensed vendor (e.g. Trestle,
Bridge, Spark, MLS Grid) naming Pegasus as their technology provider, then paste
the issued endpoint + credentials here. Pegasus never logs in to an MLS website.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import decrypt_secret
from ..db import session_scope, utcnow
from ..intel.scoring import normalize_address
from ..models import Listing, MLSConnection, Org, OrgLead, Property
from ..plans import has_feature
from ..sources.base import parse_date, parse_money, pick

log = logging.getLogger(__name__)

RESO_SELECT = ("ListingKey,StandardStatus,UnparsedAddress,StreetNumber,StreetName,StreetSuffix,City,PostalCode,"
               "StateOrProvince,Latitude,Longitude,ListPrice,ClosePrice,LivingArea,BedroomsTotal,"
               "BathroomsTotalInteger,YearBuilt,ListingContractDate,CloseDate,StatusChangeTimestamp,DaysOnMarket,"
               "ModificationTimestamp")
OFF_MARKET = {"Expired", "Withdrawn", "Canceled", "Cancelled"}


def _token(conn: MLSConnection, client: httpx.Client) -> str:
    secret = decrypt_secret(conn.secret_enc)
    if not conn.token_url:  # vendor issued a long-lived bearer token
        return secret or ""
    resp = client.post(conn.token_url, data={"grant_type": "client_credentials", "client_id": conn.client_id,
                                             "client_secret": secret, "scope": "api"})
    resp.raise_for_status()
    return resp.json()["access_token"]


def normalize_listing(row: dict) -> dict | None:
    key = pick(row, ["ListingKey", "ListingId", "MLS #", "MLS Number", "MLSNumber", "listing_id"])
    if not key:
        return None
    address = pick(row, ["UnparsedAddress", "Address", "Full Address", "address"])
    if not address:
        parts = [pick(row, ["StreetNumber"]), pick(row, ["StreetName"]), pick(row, ["StreetSuffix"])]
        address = " ".join(str(p) for p in parts if p) or None
    status = str(pick(row, ["StandardStatus", "Status", "MlsStatus", "status"]) or "").strip().title()
    status = {"Sold": "Closed", "Active Under Contract": "Pending", "Cancelled": "Canceled"}.get(status, status)

    def num(names):
        value = pick(row, names)
        try:
            return float(str(value).replace(",", "").replace("$", "")) if value not in (None, "") else None
        except ValueError:
            return None

    return {
        "listing_key": str(key), "status": status or "Unknown", "address": address,
        "city": pick(row, ["City", "city"]), "zip": str(pick(row, ["PostalCode", "Zip", "zip"]) or "")[:10] or None,
        "lat": num(["Latitude", "lat"]), "lng": num(["Longitude", "lng"]),
        "list_price": parse_money(pick(row, ["ListPrice", "List Price"])),
        "close_price": parse_money(pick(row, ["ClosePrice", "Sold Price", "Close Price"])),
        "sqft": int(num(["LivingArea", "SqFt", "Square Feet"]) or 0) or None,
        "beds": num(["BedroomsTotal", "Beds"]), "baths": num(["BathroomsTotalInteger", "Baths"]),
        "year_built": int(num(["YearBuilt", "Year Built"]) or 0) or None,
        "list_date": parse_date(pick(row, ["ListingContractDate", "List Date", "OnMarketDate"])),
        "close_date": parse_date(pick(row, ["CloseDate", "Close Date", "Sold Date"])),
        "status_changed_at": parse_date(pick(row, ["StatusChangeTimestamp", "Status Change Date"])),
        "days_on_market": int(num(["DaysOnMarket", "DOM"]) or 0) or None,
    }


def upsert_listing(session: Session, conn: MLSConnection, data: dict) -> tuple[Listing, bool]:
    lst = session.scalar(select(Listing).where(Listing.connection_id == conn.id,
                                               Listing.listing_key == data["listing_key"]))
    created = lst is None
    if created:
        lst = Listing(org_id=conn.org_id, connection_id=conn.id, listing_key=data["listing_key"])
        session.add(lst)
    previous = lst.status
    for k, v in data.items():
        if k != "listing_key":
            setattr(lst, k, v)
    norm = normalize_address(lst.address)
    if norm and norm[0].isdigit():
        prop = session.scalar(select(Property).where(Property.norm_address == norm,
                                                     (Property.zip == (lst.zip or "")[:5]) | Property.zip.is_(None)))
        if prop is None:
            prop = Property(norm_address=norm, address=lst.address, city=lst.city, zip=(lst.zip or "")[:5] or None,
                            lat=lst.lat, lng=lst.lng, distress=[], data={})
            session.add(prop)
            session.flush()
        lst.property_id = prop.id
    session.flush()
    org = session.get(Org, conn.org_id)
    if lst.status in OFF_MARKET and previous != lst.status and lst.property_id and org and has_feature(org, "expired_listings"):
        _expired_lead(session, org, lst)
    return lst, created


def _expired_lead(session: Session, org: Org, lst: Listing) -> None:
    ref = f"h:{lst.property_id}"
    lead = session.scalar(select(OrgLead).where(OrgLead.org_id == org.id, OrgLead.ref == ref))
    if lead is None:
        lead = OrgLead(org_id=org.id, ref=ref, lead_type="property", property_id=lst.property_id,
                       trade="real_estate_agent", status="new", visible_at=utcnow())
        session.add(lead)
    recent = lst.status_changed_at and lst.status_changed_at >= utcnow() - timedelta(days=30)
    lead.score = 88 if recent else 70
    lead.reasons = [f"Listing {lst.status.lower()}", f"Was ${lst.list_price:,.0f}" if lst.list_price else "MLS"]


def sync_connection(connection_id: int, client: httpx.Client | None = None) -> dict:
    with session_scope() as session:
        conn = session.get(MLSConnection, connection_id)
        if conn is None or conn.vendor != "reso":
            return {"skipped": True}
        own = client is None
        client = client or httpx.Client(timeout=60)
        created = updated = 0
        try:
            token = _token(conn, client)
            since = (conn.last_sync_at or utcnow() - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
            url = f"{conn.base_url.rstrip('/')}/Property"
            params: dict | None = {"$filter": f"ModificationTimestamp gt {since}", "$select": RESO_SELECT,
                                   "$top": 200, "$orderby": "ModificationTimestamp"}
            pages = 0
            while url and pages < 200:
                resp = client.get(url, params=params, headers={"Authorization": f"Bearer {token}",
                                                               "Accept": "application/json"})
                resp.raise_for_status()
                body = resp.json()
                for row in body.get("value", []):
                    data = normalize_listing(row)
                    if data:
                        _, was_new = upsert_listing(session, conn, data)
                        created += was_new
                        updated += not was_new
                url, params, pages = body.get("@odata.nextLink"), None, pages + 1
            conn.status, conn.last_error, conn.last_sync_at = "active", None, utcnow()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            conn.status, conn.last_error = "error", f"{type(exc).__name__}: {exc}"[:1000]
            log.warning("MLS sync %s failed: %s", connection_id, exc)
        finally:
            if own:
                client.close()
        return {"created": created, "updated": updated, "status": conn.status}


def import_csv(session: Session, conn: MLSConnection, content: bytes) -> dict:
    text = content.decode("utf-8-sig", errors="replace")
    created = updated = skipped = 0
    for row in csv.DictReader(io.StringIO(text)):
        data = normalize_listing(row)
        if not data:
            skipped += 1
            continue
        _, was_new = upsert_listing(session, conn, data)
        created += was_new
        updated += not was_new
    conn.status, conn.last_sync_at = "active", utcnow()
    return {"created": created, "updated": updated, "skipped": skipped}
