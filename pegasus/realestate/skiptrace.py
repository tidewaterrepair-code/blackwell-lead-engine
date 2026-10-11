"""Skip tracing (owner phone/email) through BatchData, paid with credits.

Each phone comes back with DNC / litigator flags; flagged numbers are shown
as "do not call" so outreach stays TCPA-safe. Opted-out people are suppressed.
"""

from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..billing import InsufficientCredits, add_credits, spend_credits
from ..config import get_settings
from ..models import Contact, OptOut, Org, Property, Signal

log = logging.getLogger(__name__)
BATCHDATA_URL = "https://api.batchdata.com/api/v1/property/skip-trace"
COST = 1


class SkipTraceError(Exception):
    pass


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


def parse_batchdata(data: dict) -> dict | None:
    """Defensive parse of a BatchData skip-trace response into {name, phones, emails, mailing}."""
    results = (data.get("results") or {})
    persons = results.get("persons") or (results.get("data") or [{}])[0].get("persons") or []
    if not persons:
        return None
    person = persons[0]
    name = person.get("name") or {}
    full = name.get("full") or " ".join(filter(None, [name.get("first"), name.get("last")])) or None
    phones = []
    for p in person.get("phoneNumbers") or person.get("phones") or []:
        number = p.get("number") or p.get("phoneNumber")
        if not number:
            continue
        phones.append({
            "number": number, "type": (p.get("type") or "").lower() or None,
            "dnc": bool(p.get("dnc") or p.get("doNotCall")),
            "litigator": bool(p.get("tcpa") or p.get("litigator")),
            "score": p.get("score"),
        })
    emails = [e.get("email") if isinstance(e, dict) else e for e in person.get("emails") or [] if e]
    mailing = person.get("mailingAddress") or {}
    mail = ", ".join(filter(None, [mailing.get("street"), mailing.get("city"), mailing.get("state"),
                                   mailing.get("zip")])) or None
    return {"name": full, "phones": phones, "emails": [e for e in emails if e], "mailing": mail}


def _call_batchdata(address: dict, client: httpx.Client | None = None) -> dict:
    key = get_settings().batchdata_api_key
    if not key:
        raise SkipTraceError("Contact lookups aren't switched on yet (set BATCHDATA_API_KEY).")
    own = client is None
    client = client or httpx.Client(timeout=45)
    try:
        resp = client.post(BATCHDATA_URL, headers={"Authorization": f"Bearer {key}"},
                           json={"requests": [{"propertyAddress": address}]})
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise SkipTraceError("The contact lookup service didn't respond. You weren't charged.") from exc
    finally:
        if own:
            client.close()


def skip_trace(session: Session, org: Org, *, prop: Property | None, sig: Signal | None,
               client: httpx.Client | None = None) -> Contact:
    target = prop or (sig.property if sig else None)
    address = target.address if target else (sig.address if sig else None)
    if not address:
        raise SkipTraceError("This lead has no street address to look up.")
    existing = session.scalar(select(Contact).where(Contact.org_id == org.id, (
        (Contact.property_id == target.id) if target else (Contact.signal_id == sig.id))))
    if existing:
        return existing
    if (org.credits or 0) < COST:
        raise InsufficientCredits("You're out of contact credits. Add a credit pack in Billing.")
    city = (target.city if target else None) or (sig.city if sig else None)
    state = (target.state if target else None) or (sig.state if sig else None)
    zip_code = (target.zip if target else None) or (sig.zip if sig else None)
    data = _call_batchdata({"street": address, "city": city, "state": state, "zip": zip_code}, client)
    parsed = parse_batchdata(data)
    if not parsed or not (parsed["phones"] or parsed["emails"]):
        raise SkipTraceError("No contact info found for this owner. You weren't charged.")
    suppressed_phones = {_digits(p) for p in session.scalars(select(OptOut.phone).where(OptOut.phone.is_not(None)))}
    phones = [p for p in parsed["phones"] if _digits(p["number"]) not in suppressed_phones]
    contact = Contact(org_id=org.id, property_id=target.id if target else None, signal_id=sig.id if sig else None,
                      name=parsed["name"], phones=phones, emails=parsed["emails"], mailing_address=parsed["mailing"],
                      provider="batchdata", credits_spent=COST)
    session.add(contact)
    session.flush()
    spend_credits(session, org, COST, "skip_trace", f"contact:{contact.id}")
    return contact


def refund(session: Session, org: Org, contact: Contact, reason: str = "bad data") -> None:
    add_credits(session, org, contact.credits_spent, "refund", f"contact:{contact.id}:{reason}")
    contact.credits_spent = 0
