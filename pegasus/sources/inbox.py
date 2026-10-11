"""Homeowner requests from an email inbox (IMAP), free with any Gmail account.

Point saved-search alerts (Craigslist "services wanted", Nextdoor/Facebook
notification emails, Angi/Thumbtack/HomeAdvisor lead emails, your website's
contact form) at a Gmail label, and this adapter turns each message into a lead.

sources.yaml:
    email-requests:
      type: imap
      kind: request
      host: imap.gmail.com
      user: ${IMAP_USER}
      password: ${IMAP_PASSWORD}      # Gmail app password
      folder: Leads                   # Gmail label name
"""

from __future__ import annotations

import email
import imaplib
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterable

from .base import Adapter, LeadInput, RawItem, clean, find_city, find_email, find_phone, parse_date
from .feeds import html_to_text


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, LookupError):
        return value


def message_body(msg: email.message.Message) -> str:
    plain, html = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and html is None:
            html = text
    return (plain or html_to_text(html) or "").strip()


def parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    try:
        date = parsedate_to_datetime(msg.get("Date")).isoformat() if msg.get("Date") else None
    except (TypeError, ValueError):
        date = None
    return {
        "message_id": (msg.get("Message-ID") or "").strip(),
        "subject": _decode(msg.get("Subject")),
        "from": _decode(msg.get("From")),
        "reply_to": _decode(msg.get("Reply-To")),
        "date": date,
        "body": message_body(msg)[:8000],
    }


class IMAPAdapter(Adapter):
    kind = "request"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        cfg = self.config
        conn = imaplib.IMAP4_SSL(cfg.get("host", "imap.gmail.com"), int(cfg.get("port", 993)))
        try:
            conn.login(cfg["user"], cfg["password"])
            status, _ = conn.select(f'"{cfg.get("folder", "INBOX")}"', readonly=True)
            if status != "OK":
                raise RuntimeError(f"IMAP folder not found: {cfg.get('folder')}")
            _, data = conn.search(None, "SINCE", since.strftime("%d-%b-%Y"))
            for num in (data[0] or b"").split():
                _, parts = conn.fetch(num, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if not raw:
                    continue
                payload = parse_message(raw)
                ext = payload["message_id"] or f"{payload['date']}|{payload['subject']}"
                yield RawItem(external_id=ext[:280], payload=payload)
        finally:
            try:
                conn.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    def normalize(self, payload: dict) -> LeadInput | None:
        subject = clean(payload.get("subject")) or "(no subject)"
        body = payload.get("body") or ""
        name, sender = parseaddr(payload.get("reply_to") or payload.get("from") or "")
        skip_senders = [s.lower() for s in self.config.get("ignore_senders", [])]
        if sender and any(s in sender.lower() for s in skip_senders):
            return None
        # Prefer contact details written in the body (platform emails come from noreply@).
        contact_email = find_email(body) or (sender if "noreply" not in sender.lower() else None)
        return LeadInput(
            external_id=(payload.get("message_id") or f"{payload.get('date')}|{subject}")[:280],
            kind=self.kind,
            title=subject[:480],
            description=body[:4000],
            contact_name=clean(name),
            email=contact_email,
            phone=find_phone(body),
            city=find_city(f"{subject} {body}"),
            posted_at=parse_date(payload.get("date")),
            hints=list(self.config.get("hints", [])),
        )
