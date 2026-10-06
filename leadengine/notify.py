"""Free notifications: daily email digest over SMTP (e.g. Gmail app password)
and instant phone pushes for hot leads via ntfy (https://ntfy.sh, free app)."""

from __future__ import annotations

import html
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import Lead, session_scope, utcnow

log = logging.getLogger(__name__)


def send_email(subject: str, text: str, html_body: str) -> bool:
    s = get_settings()
    if not (s.smtp_host and s.digest_to):
        log.info("email not configured (SMTP_HOST / DIGEST_TO); skipping")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.digest_from or s.digest_to
    msg["To"] = s.digest_to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    if s.smtp_port == 465:
        smtp_conn = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30)
    else:
        smtp_conn = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
    with smtp_conn as smtp:
        if s.smtp_port != 465:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        smtp.send_message(msg)
    return True


def send_push(title: str, message: str, url: str | None = None, priority: str = "default") -> bool:
    s = get_settings()
    if not s.ntfy_url:
        return False
    headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority, "Tags": "hammer"}
    if url:
        headers["Click"] = url
    resp = httpx.post(s.ntfy_url, content=message.encode(), headers=headers, timeout=20)
    resp.raise_for_status()
    return True


def lead_url(lead: Lead) -> str:
    return f"{get_settings().public_url}/leads/{lead.id}"


def _line(lead: Lead) -> str:
    bits = [f"[{lead.score}] {lead.job_label}", lead.title]
    if lead.est_value:
        bits.append(f"${lead.est_value:,.0f}")
    if lead.due_at:
        bits.append(f"due {lead.due_at:%b %d}")
    return " · ".join(bits)


def build_digest(leads: list[Lead]) -> tuple[str, str, str]:
    subject = f"{len(leads)} new construction lead{'s' if len(leads) != 1 else ''}"
    text = "\n".join(f"{_line(l)}\n  {lead_url(l)}" for l in leads)
    rows = "".join(
        f"<tr><td style='padding:6px 10px;font-weight:bold'>{l.score}</td>"
        f"<td style='padding:6px 10px'>{html.escape(l.job_label)}<br><small>{html.escape(l.customer_label)}</small></td>"
        f"<td style='padding:6px 10px'><a href='{lead_url(l)}'>{html.escape(l.title)}</a>"
        f"<br><small>{html.escape(l.city or '')}{' · $' + format(l.est_value, ',.0f') if l.est_value else ''}</small></td></tr>"
        for l in leads
    )
    html_body = (
        "<div style='font-family:sans-serif'><h2>New leads</h2>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        f"<p><a href='{get_settings().public_url}'>Open dashboard</a></p></div>"
    )
    return subject, text, html_body


def send_digest(hours: int = 24) -> int:
    s = get_settings()
    with session_scope() as session:
        leads = session.scalars(
            select(Lead)
            .where(
                Lead.created_at >= utcnow() - timedelta(hours=hours),
                Lead.score >= s.digest_min_score,
                Lead.duplicate_of_id.is_(None),
                Lead.status == "new",
            )
            .order_by(Lead.score.desc())
            .limit(50)
        ).all()
        if not leads:
            log.info("digest: nothing new")
            return 0
        subject, text, html_body = build_digest(leads)
        sent = send_email(subject, text, html_body)
        if not sent and s.ntfy_url:
            send_push(subject, "\n".join(_line(l) for l in leads[:10]), s.public_url)
        return len(leads)


def push_hot_leads() -> int:
    s = get_settings()
    if not s.ntfy_url:
        return 0
    count = 0
    with session_scope() as session:
        leads = session.scalars(
            select(Lead)
            .where(Lead.notified_at.is_(None), Lead.score >= s.hot_lead_score, Lead.duplicate_of_id.is_(None),
                   Lead.status == "new", Lead.created_at >= utcnow() - timedelta(days=2))
            .order_by(Lead.score.desc())
            .limit(10)
        ).all()
        for lead in leads:
            try:
                send_push(f"Hot lead: {lead.job_label} ({lead.score})", _line(lead), lead_url(lead), "high")
            except httpx.HTTPError as exc:
                log.warning("ntfy push failed: %s", exc)
                break
            lead.notified_at = utcnow()
            count += 1
    return count
