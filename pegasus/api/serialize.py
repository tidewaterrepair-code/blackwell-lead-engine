"""JSON shapes returned by the API."""

from __future__ import annotations

from datetime import datetime

from ..accounts import level_for
from ..intel.taxonomy import tag_label, trades as trade_defs
from ..models import LEAD_STATUSES, SIGNAL_KINDS, OrgLead, Property, Signal, Territory
from ..plans import has_feature


def iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def property_dict(prop: Property | None, *, full: bool = False) -> dict | None:
    if prop is None:
        return None
    out = {
        "id": prop.id, "address": prop.address, "city": prop.city, "state": prop.state, "zip": prop.zip,
        "lat": prop.lat, "lng": prop.lng, "motivation": prop.motivation_score,
        "sell_probability": prop.sell_probability, "distress": prop.distress or [],
        "factors": (prop.data or {}).get("factors", []), "absentee": prop.absentee, "vacant": prop.vacant,
        "year_built": prop.year_built, "sqft": prop.sqft, "est_value": prop.est_value,
        "equity_est": prop.equity_est,
    }
    if full:
        out.update({
            "parcel_id": prop.parcel_id, "owner_name": prop.owner_name,
            "owner_mailing_address": prop.owner_mailing_address, "assessed_value": prop.assessed_value,
            "last_sale_date": iso(prop.last_sale_date), "last_sale_price": prop.last_sale_price,
            "mortgage_est": prop.mortgage_est, "beds": prop.beds, "baths": prop.baths,
        })
    return out


def signal_dict(sig: Signal, *, full: bool = False) -> dict:
    out = {
        "id": sig.id, "kind": sig.kind, "kind_label": SIGNAL_KINDS.get(sig.kind, sig.kind), "title": sig.title,
        "tag": sig.primary_tag, "tag_label": tag_label(sig.primary_tag),
        "tags": [{"key": t, "label": tag_label(t)} for t in (sig.tags or [])],
        "address": sig.address, "city": sig.city, "state": sig.state, "zip": sig.zip, "lat": sig.lat, "lng": sig.lng,
        "value": sig.est_value, "posted_at": iso(sig.posted_at or sig.created_at), "due_at": iso(sig.due_at),
        "contractor": sig.contractor_name, "commercial": sig.commercial, "url": sig.url,
    }
    if full:
        out.update({
            "description": sig.description, "permit_type": sig.permit_type, "owner_name": sig.owner_name,
            "contact_name": sig.contact_name, "phone": sig.phone, "email": sig.email, "source_id": sig.source_id,
            "classified_by": sig.classified_by, "confidence": sig.confidence,
            "facts": (sig.data or {}).get("facts", {}),
        })
    return out


def lead_dict(lead: OrgLead, org, *, full: bool = False) -> dict:
    sig = lead.signal
    pred = lead.prediction
    trade = trade_defs().get(lead.trade or "")
    out = {
        "id": lead.id, "type": lead.lead_type, "status": lead.status, "status_label": LEAD_STATUSES.get(lead.status),
        "score": lead.score, "reasons": lead.reasons or [], "trade": lead.trade,
        "trade_label": trade.label if trade else None, "created_at": iso(lead.created_at),
        "follow_up_at": iso(lead.follow_up_at), "value_won": lead.value_won, "locked": False,
        "signal": signal_dict(sig, full=full) if sig else None,
        "property": property_dict(sig.property if sig else None, full=full),
    }
    if pred:
        out["prediction"] = {
            "tag": pred.tag, "tag_label": tag_label(pred.tag), "window_start": iso(pred.window_start),
            "window_end": iso(pred.window_end), "probability": pred.probability, "reason": pred.reason,
        }
        if not has_feature(org, "predictions"):
            # Teaser: show that a forecast exists, hide where it is.
            out["locked"] = True
            if out["signal"]:
                out["signal"].update({"address": None, "title": f"Predicted {tag_label(pred.tag).lower()} job",
                                      "lat": None, "lng": None, "url": None, "description": None,
                                      "contractor": None, "owner_name": None})
            out["property"] = None
    return out


def territory_dict(t: Territory) -> dict:
    return {"id": t.id, "name": t.name, "kind": t.kind, "data": t.data, "trades": t.trades or [],
            "exclusive": t.exclusive, "created_at": iso(t.created_at)}


def user_dict(user) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "phone": user.phone, "is_admin": user.is_admin,
            "xp": user.xp, "level": level_for(user.xp or 0), "streak": user.streak_days or 0,
            "badges": user.badges or []}
