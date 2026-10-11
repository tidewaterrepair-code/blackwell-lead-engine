"""Email (SMTP) and push (ntfy) notifications: magic links, morning digests, hot-lead alerts."""

from __future__ import annotations

import html
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from email.utils import make_msgid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .intel.taxonomy import tag_label
from .models import Membership, Org, OrgLead, User

log = logging.getLogger(__name__)
OUTBOX: list[dict] = []  # captured messages when SMTP isn't configured (dev + tests)

BRAND_GRADIENT = "linear-gradient(135deg,#7C5CFF,#22D3EE)"


def send_email(to: str, subject: str, text: str, html_body: str | None = None) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, s.mail_from, to
    msg["Message-ID"] = make_msgid(domain="pegasusleads.com")
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    if not s.smtp_host:
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html_body})
        log.info("email (not sent, SMTP not configured) to=%s subject=%s", to, subject)
        return False
    conn = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30) if s.smtp_port == 465 else \
        smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
    with conn as smtp:
        if s.smtp_port != 465:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        smtp.send_message(msg)
    return True


def send_push(topic: str, title: str, message: str, url: str | None = None, priority: str = "default") -> bool:
    if not topic:
        return False
    headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority, "Tags": "zap"}
    if url:
        headers["Click"] = url
    resp = httpx.post(f"{get_settings().ntfy_base_url}/{topic}", content=message.encode(), headers=headers,
                      timeout=20)
    resp.raise_for_status()
    return True


def wrap_html(title: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None) -> str:
    cta = (f"<p style='margin:28px 0'><a href='{html.escape(cta_url)}' style='background:#7C5CFF;color:#fff;"
           f"padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600'>{html.escape(cta_label)}</a></p>"
           if cta_label and cta_url else "")
    return (
        "<div style='background:#0A0F2C;padding:32px 12px;font-family:Inter,Segoe UI,Arial,sans-serif'>"
        "<div style='max-width:560px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden'>"
        f"<div style='background:{BRAND_GRADIENT};padding:20px 28px;color:#fff;font-weight:700;font-size:18px'>"
        "Pegasus</div>"
        f"<div style='padding:28px;color:#0A0F2C;font-size:15px;line-height:1.55'><h2 style='margin:0 0 12px'>"
        f"{html.escape(title)}</h2>{body_html}{cta}</div>"
        "<div style='padding:16px 28px;color:#6b7280;font-size:12px;border-top:1px solid #eef0f6'>"
        "Pegasus · data &amp; lead technology · You can change email settings in the app.</div></div></div>"
    )


def send_magic_link(email: str, url: str) -> bool:
    text = f"Tap to sign in to Pegasus:\n\n{url}\n\nThe link works for 30 minutes. If you didn't ask for it, ignore this."
    body = "<p>Tap the button to sign in. The link works for 30 minutes.</p>"
    return send_email(email, "Your Pegasus sign-in link", text, wrap_html("Sign in to Pegasus", body, "Sign in", url))


def send_invite(email: str, org_name: str, url: str) -> bool:
    text = f"You've been invited to join {org_name} on Pegasus:\n\n{url}"
    return send_email(email, f"Join {org_name} on Pegasus", text,
                      wrap_html(f"Join {org_name} on Pegasus", "<p>Your team uses Pegasus to find jobs first.</p>",
                                "Accept invite", url))


def _lead_line(lead: OrgLead) -> tuple[str, str]:
    sig = lead.signal
    title = sig.title if sig else "Lead"
    if lead.prediction:
        title = f"Predicted: {tag_label(lead.prediction.tag)} · {sig.address or sig.city or ''}"
    meta = " · ".join(filter(None, [tag_label(sig.primary_tag) if sig else None, sig.city if sig else None,
                                    f"${sig.est_value:,.0f}" if sig and sig.est_value else None]))
    return title, meta


def org_recipients(session: Session, org: Org) -> list[User]:
    return list(session.scalars(select(User).join(Membership, Membership.user_id == User.id)
                                .where(Membership.org_id == org.id)))


def send_digest(session: Session, org: Org, hours: int = 24) -> int:
    if not (org.settings or {}).get("digest", True):
        return 0
    now = utcnow()
    leads = session.scalars(
        select(OrgLead).where(OrgLead.org_id == org.id, OrgLead.status == "new",
                              OrgLead.created_at >= now - timedelta(hours=hours), OrgLead.visible_at <= now)
        .order_by(OrgLead.score.desc()).limit(15)
    ).all()
    if not leads:
        return 0
    base = get_settings().public_url
    rows_html, rows_text = [], []
    for lead in leads:
        title, meta = _lead_line(lead)
        url = f"{base}/app/leads/{lead.id}"
        rows_html.append(
            f"<tr><td style='padding:10px 8px;font-weight:700;color:#7C5CFF;font-size:18px'>{lead.score}</td>"
            f"<td style='padding:10px 8px'><a href='{url}' style='color:#0A0F2C;font-weight:600;text-decoration:none'>"
            f"{html.escape(title)}</a><br><span style='color:#6b7280;font-size:13px'>{html.escape(meta)}</span></td></tr>")
        rows_text.append(f"[{lead.score}] {title} ({meta})\n  {url}")
    subject = f"☀️ {len(leads)} new lead{'s' if len(leads) != 1 else ''} in your area"
    body = f"<table style='border-collapse:collapse;width:100%'>{''.join(rows_html)}</table>"
    sent = 0
    for user in org_recipients(session, org):
        send_email(user.email, subject, "\n".join(rows_text),
                   wrap_html("Your Morning Drop", body, "Open Pegasus", f"{base}/app"))
        sent += 1
    return sent


def push_hot_leads(session: Session) -> int:
    """ntfy push for fresh high-score leads (per org setting)."""
    count = 0
    for org in session.scalars(select(Org)):
        topic = (org.settings or {}).get("ntfy_topic")
        if not topic:
            continue
        threshold = int((org.settings or {}).get("alerts_min_score", 75))
        leads = session.scalars(select(OrgLead).where(
            OrgLead.org_id == org.id, OrgLead.notified_at.is_(None), OrgLead.score >= threshold,
            OrgLead.status == "new", OrgLead.visible_at <= utcnow(),
            OrgLead.created_at >= utcnow() - timedelta(days=2)).order_by(OrgLead.score.desc()).limit(5)).all()
        for lead in leads:
            title, meta = _lead_line(lead)
            try:
                send_push(topic, f"🔥 {lead.score} · {title}"[:120], meta,
                          f"{get_settings().public_url}/app/leads/{lead.id}", "high")
            except httpx.HTTPError as exc:
                log.warning("ntfy push failed: %s", exc)
                break
            lead.notified_at = utcnow()
            count += 1
    return count
