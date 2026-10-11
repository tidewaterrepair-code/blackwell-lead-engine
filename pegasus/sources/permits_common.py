"""Field-mapping normalizer shared by tabular feeds (Socrata, ArcGIS, CSV).

Works for any signal kind (permits, sales, code violations, tax lists...):
set `kind:` on the source and map whichever fields the dataset has.

Every city names its columns differently. Each logical field has a list of
common column names; a source can override any of them in sources.yaml:

    fields:
      description: [work_description, description_of_work]
      est_value: project_cost
"""

from __future__ import annotations

from .base import LeadInput, clean, parse_date, parse_money, pick

DEFAULT_FIELDS: dict[str, list[str]] = {
    "external_id": ["permit_number", "permitnumber", "permit_no", "permit_num", "record_number", "record_id",
                    "recordid", "case_number", "application_number", "permit", "objectid", "id"],
    "description": ["work_description", "workdesc", "description", "work_desc", "project_description",
                    "projectdescription", "scope_of_work", "scope", "permit_description", "comments",
                    "proposed_use", "project_name"],
    "permit_type": ["permit_type", "permittype", "type", "record_type", "recordtype", "permit_type_desc",
                    "category", "permit_category", "work_class", "permit_class"],
    "work_type": ["work_type", "worktype", "construction_type", "constructiontype", "use_type", "usetype",
                  "use_class", "useclass", "structure", "occupancy", "sub_type", "subtype", "class"],
    "address": ["address", "full_address", "fulladdress", "site_address", "siteaddress", "street_address",
                "streetaddress", "location_address", "property_address", "original_address1", "addr",
                "location"],
    "city": ["city", "original_city", "site_city", "municipality"],
    "zip": ["zip", "zipcode", "zip_code", "postal_code", "original_zip"],
    "est_value": ["project_cost", "projectcost", "valuation", "job_value", "jobvalue", "estimated_cost",
                  "estimatedcost", "construction_value", "est_value", "value", "declared_value",
                  "total_valuation", "cost"],
    "owner_name": ["owner_name", "ownername", "owner", "property_owner", "applicant_name", "applicant"],
    "contractor_name": ["contractor_name", "contractorname", "contractor", "contractor_company",
                        "contractorcompanyname", "business_name", "company_name"],
    "phone": ["contractor_phone", "contractorphone", "applicant_phone", "phone"],
    "status": ["status", "permit_status", "current_status", "statuscurrent"],
    "posted_at": ["issue_date", "issuedate", "issued_date", "date_issued", "application_date",
                  "applicationdate", "applied_date", "applieddate", "file_date", "filed_date",
                  "created_date", "createddate", "status_date", "date"],
    # Extra descriptive columns; every one present is fed to the classifier.
    "extra": ["structure", "use_type", "usetype", "use_class", "useclass", "occupancy", "sub_type", "subtype",
              "construction_type", "constructiontype", "work_class", "proposed_use", "project_name",
              "work_type", "worktype", "category"],
    "state": ["state", "site_state", "original_state"],
    # Property facts (real estate signals).
    "parcel_id": ["parcel_id", "parcelid", "parcel", "gpin", "pin", "apn", "tax_map", "account_number",
                  "tax_account", "re_number"],
    "year_built": ["year_built", "yearbuilt", "yr_built", "built_year"],
    "sqft": ["sqft", "living_area", "livingarea", "finished_sqft", "building_sqft", "gross_area", "heated_area"],
    "sale_price": ["sale_price", "saleprice", "price", "consideration", "sales_price", "transfer_amount"],
    "sale_date": ["sale_date", "saledate", "deed_date", "transfer_date", "recording_date", "recorded_date"],
    "mailing_address": ["mailing_address", "mailingaddress", "owner_address", "owneraddress", "mail_address",
                        "owner_mailing_address"],
    "owner_state": ["owner_state", "mailing_state", "mail_state"],
    "assessed_value": ["assessed_value", "assessedvalue", "total_value", "totalvalue", "appraised_value",
                       "market_value", "total_assessment"],
    "amount_due": ["amount_due", "amountdue", "balance_due", "delinquent_amount", "taxes_due", "total_due"],
    "case_number": ["case_number", "casenumber", "case_no", "violation_number", "complaint_number"],
    "lat": ["latitude", "lat", "y", "_lat"],
    "lng": ["longitude", "lng", "lon", "long", "x", "_lng"],
}


def field_names(config: dict, name: str) -> list[str]:
    override = (config.get("fields") or {}).get(name)
    defaults = DEFAULT_FIELDS.get(name, [])
    if override is None:
        return defaults
    return ([override] if isinstance(override, str) else list(override)) + defaults


def get(record: dict, config: dict, name: str):
    return pick(record, field_names(config, name))


KIND_TITLES = {"permit": "Permit", "sale": "Sold", "violation": "Code violation",
               "tax_delinquent": "Tax delinquent", "foreclosure": "Pre-foreclosure", "probate": "Probate",
               "eviction": "Eviction filing", "bid": "Bid", "subdivision": "Subdivision"}
FACT_FIELDS = ("parcel_id", "year_built", "sqft", "sale_price", "sale_date", "mailing_address", "owner_state",
               "assessed_value", "amount_due", "case_number")


def normalize_permit(record: dict, config: dict, *, default_city: str | None, url_template: str | None = None
                     ) -> LeadInput | None:
    kind = config.get("kind", "permit")
    external_id = clean(get(record, config, "external_id"))
    if not external_id and kind != "permit":
        # Property-centric datasets often have no record id: parcel + date is unique enough.
        parts = [clean(get(record, config, "parcel_id")), clean(get(record, config, "address")),
                 clean(get(record, config, "sale_date")) or clean(get(record, config, "posted_at"))]
        external_id = "|".join(p for p in parts if p) or None
    if not external_id:
        return None
    description = clean(get(record, config, "description"))
    permit_type = clean(get(record, config, "permit_type"))
    work_type = clean(get(record, config, "work_type"))
    status = clean(get(record, config, "status"))

    skip_status = [s.lower() for s in config.get("skip_statuses", ["void", "withdrawn", "cancelled", "canceled",
                                                                   "denied", "expired", "revoked"])]
    if kind == "permit" and status and status.lower() in skip_status:
        return None

    address = clean(get(record, config, "address"))
    lat = _float(get(record, config, "lat"))
    lng = _float(get(record, config, "lng"))
    location = pick(record, ["location", "geocoded_column", "the_geom", "point"])
    if isinstance(location, dict) and lat is None:
        if "coordinates" in location:  # GeoJSON point
            lng, lat = (_float(c) for c in location["coordinates"][:2])
        else:
            lat, lng = _float(location.get("latitude")), _float(location.get("longitude"))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        lat = lng = None  # missing, or projected coordinates rather than lat/lng

    title_parts = [p for p in (permit_type, work_type) if p]
    title = " · ".join(title_parts) or KIND_TITLES.get(kind, kind.replace("_", " ").title())
    if address:
        title = f"{title} — {address}"

    url = None
    if url_template:
        try:
            url = url_template.format_map({**record, "id": external_id})
        except (KeyError, IndexError, ValueError):
            url = None

    facts = {}
    for name in FACT_FIELDS:
        value = get(record, config, name)
        if value not in (None, ""):
            facts[name] = clean(value) if not isinstance(value, (int, float)) else value
    est_value = parse_money(get(record, config, "est_value"))
    if kind == "sale" and est_value is None:
        est_value = parse_money(facts.get("sale_price"))
    posted_at = parse_date(get(record, config, "posted_at"))
    if posted_at is None and facts.get("sale_date"):
        posted_at = parse_date(facts["sale_date"])

    return LeadInput(
        external_id=external_id,
        kind=kind,
        title=title[:480],
        description=description,
        permit_type=" / ".join(title_parts) or None,
        address=address,
        city=clean(get(record, config, "city")) or default_city,
        zip=(clean(get(record, config, "zip")) or "")[:10] or None,
        lat=lat,
        lng=lng,
        est_value=est_value,
        owner_name=clean(get(record, config, "owner_name")),
        contractor_name=clean(get(record, config, "contractor_name")),
        phone=clean(get(record, config, "phone")),
        url=url,
        posted_at=posted_at,
        state=(clean(get(record, config, "state")) or "")[:2].upper() or None,
        hints=extra_values(record, config),
        facts=facts,
    )


def extra_values(record: dict, config: dict) -> list[str]:
    values: list[str] = []
    for name in field_names(config, "extra"):
        value = clean(pick(record, name))
        if value and value not in values and len(value) < 300:
            values.append(value)
    return values


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
