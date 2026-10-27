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

from .auth import make_token, read_token
from .config import get_settings
from .db import utcnow
from .intel.taxonomy import tag_label
from .models import Membership, Org, OrgLead, User

log = logging.getLogger(__name__)
OUTBOX: list[dict] = []  # captured messages when SMTP isn't configured (dev + tests)
DIGEST_OFF = "digest-off"

GOLD_BUTTON = "linear-gradient(180deg,#FFE3A3,#E2B25A 55%,#B9802F)"


def send_email(to: str, subject: str, text: str, html_body: str | None = None,
               headers: dict[str, str] | None = None) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, s.mail_from, to
    msg["Message-ID"] = make_msgid(domain="getpegasus.org")
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    if not s.smtp_host:
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html_body, "headers": headers or {}})
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


# No quotes in these: they go inside single-quoted style attributes, where a quote ends the attribute early
FONT = "Inter,Segoe UI,Helvetica,Arial,sans-serif"
DISPLAY = "Oswald,Arial Narrow,Impact,Helvetica,sans-serif"
TAGLINE = "See the job before your competition does."


def wrap_html(title: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None,
              footer_html: str | None = None, art: str = "hero", preview: str | None = None) -> str:
    """Black-and-gold email shell. art: "hero" (city banner), "emblem" (ornate Pegasus) or "" (none).
    preview is the inbox snippet shown after the subject; without it clients show the first text they find."""
    brand = f"{get_settings().public_url}/static/brand"
    cta = (
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='margin:30px auto 6px'><tr>"
        f"<td align='center' bgcolor='#E2B25A' style='border-radius:12px;background:#E2B25A;"
        f"background-image:{GOLD_BUTTON};box-shadow:0 6px 24px rgba(226,178,90,.35)'>"
        f"<a href='{html.escape(cta_url)}' style='display:inline-block;padding:15px 34px;font:700 15px {FONT};"
        f"color:#1A1206;text-decoration:none;letter-spacing:.04em;text-transform:uppercase'>"
        f"{html.escape(cta_label)}</a></td></tr></table>"
        if cta_label and cta_url else "")
    if art == "emblem":  # the emblem carries its own wordmark, so it replaces the header
        header = (f"<tr><td align='center' style='padding:34px 28px 6px'><img src='{brand}/email-emblem.jpg' "
                  "width='300' alt='PEGASUS' style='display:block;width:300px;max-width:80%;height:auto;border:0;"
                  f"color:#E2B25A;font:600 26px Georgia,serif;letter-spacing:4px'></td></tr>")
    else:
        header = (f"<tr><td align='center' style='padding:24px 28px 20px'><img src='{brand}/email-wordmark.png' "
                  "width='230' height='42' alt='PEGASUS' style='display:block;border:0;color:#E2B25A;"
                  "font:600 22px Georgia,serif;letter-spacing:3px'></td></tr>")
        if art == "hero":
            header += (f"<tr><td style='padding:0;line-height:0'><img src='{brand}/email-hero.jpg' width='600' "
                       "alt='' style='display:block;width:100%;height:auto;border:0'></td></tr>")
    rule = ("<table role='presentation' cellpadding='0' cellspacing='0' border='0' align='center' "
            "style='margin:0 auto 18px'><tr><td width='56' height='2' bgcolor='#E2B25A' "
            f"style='background:#E2B25A;background-image:{GOLD_BUTTON};font-size:0;line-height:0'>&nbsp;</td></tr></table>")
    footer = footer_html or "You can change email settings in the app."
    # trailing zero-width joiners stop clients pulling body text into the snippet after the preview
    snippet = (f"<div style='display:none;max-height:0;overflow:hidden;mso-hide:all'>{html.escape(preview)}"
               f"{'&#847;&zwnj;&nbsp;' * 40}</div>" if preview else "")
    return (
        f"{snippet}<div style='margin:0;padding:0;background:#0B0A08'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' bgcolor='#0B0A08' "
        "style='background:#0B0A08;background-image:radial-gradient(ellipse at top,#2A1E0C 0%,#0B0A08 60%)'>"
        "<tr><td align='center' style='padding:32px 12px'>"
        "<table role='presentation' width='600' cellpadding='0' cellspacing='0' border='0' bgcolor='#16130F' "
        "style='width:100%;max-width:600px;background:#16130F;border:1px solid #3A2A12;border-radius:18px;"
        "overflow:hidden;box-shadow:0 0 0 1px rgba(226,178,90,.08),0 24px 60px rgba(0,0,0,.6)'>"
        f"<tr><td height='3' bgcolor='#E2B25A' style='background:#E2B25A;background-image:{GOLD_BUTTON};"
        "font-size:0;line-height:0'>&nbsp;</td></tr>"
        f"{header}"
        f"<tr><td bgcolor='#16130F' style='background:#16130F;padding:30px 36px 34px;color:#E9E0CF;"
        f"font:15px/1.65 {FONT}'>"
        f"<h1 style='margin:0 0 14px;text-align:center;font:700 26px/1.2 {DISPLAY};color:#F6EFE2;"
        f"letter-spacing:.02em'>{html.escape(title)}</h1>{rule}{body_html}{cta}</td></tr>"
        "<tr><td bgcolor='#100D0A' style='background:#100D0A;padding:22px 36px 26px;border-top:1px solid #2B2216;"
        f"text-align:center;font:13px/1.6 {FONT};color:#B8A888'>"
        f"<div style='color:#E2B25A;font:600 11px {FONT};letter-spacing:.24em;text-transform:uppercase;"
        f"margin-bottom:8px'>{TAGLINE}</div>"
        f"Pegasus · data &amp; lead technology · {footer}</td></tr>"
        "</table></td></tr></table></div>"
    )


def send_magic_link(email: str, url: str) -> bool:
    text = f"Tap to sign in to Pegasus:\n\n{url}\n\nThe link works for 30 minutes. If you didn't ask for it, ignore this."
    body = ("<p style='margin:0;text-align:center'>Tap the button to sign in. The link works for 30 minutes.</p>"
            "<p style='margin:26px 0 0;text-align:center;color:#B8A888;font-size:13px'>"
            "Didn't ask for this? You can ignore it. Nobody gets in without this link.</p>")
    return send_email(email, "Your Pegasus sign-in link", text,
                      wrap_html("Sign in to Pegasus", body, "Sign in", url, art="emblem",
                                preview="Tap to sign in. The link works for 30 minutes."))


def send_invite(email: str, org_name: str, url: str) -> bool:
    text = f"You've been invited to join {org_name} on Pegasus:\n\n{url}"
    body = (f"<p style='margin:0;text-align:center'><b style='color:#E2B25A'>{html.escape(org_name)}</b> uses Pegasus "
            "to see jobs and listings before anyone else. Accept the invite to get the same head start.</p>")
    return send_email(email, f"Join {org_name} on Pegasus", text,
                      wrap_html(f"Join {org_name} on Pegasus", body, "Accept invite", url, art="emblem",
                                preview=f"{org_name} wants you on their Pegasus team."))


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
        hot = lead.score >= 75
        rows_html.append(
            "<tr><td width='54' valign='top' style='padding:14px 0;border-bottom:1px solid #2B2216'>"
            f"<div style='width:44px;height:44px;line-height:44px;border-radius:12px;text-align:center;font:700 17px {FONT};"
            f"color:{'#1A1206' if hot else '#E2B25A'};background:{'#E2B25A' if hot else '#221B12'};"
            f"{f'background-image:{GOLD_BUTTON};' if hot else 'border:1px solid #3A2A12;'}'>{lead.score}</div></td>"
            "<td valign='middle' style='padding:14px 0 14px 12px;border-bottom:1px solid #2B2216'>"
            f"<a href='{url}' style='color:#F6EFE2;font-weight:600;text-decoration:none'>{html.escape(title)}</a><br>"
            f"<span style='color:#A8987C;font-size:13px'>{html.escape(meta)}</span></td></tr>")
        rows_text.append(f"[{lead.score}] {title} ({meta})\n  {url}")
    subject = f"☀️ {len(leads)} new lead{'s' if len(leads) != 1 else ''} in your area"
    body = (f"<p style='margin:0 0 8px;text-align:center;color:#A8987C'>Fresh overnight and ranked by score. "
            f"Call the top ones first.</p>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
            f"style='border-collapse:collapse;width:100%'>{''.join(rows_html)}</table>")
    preview = f"{len(leads)} new · top score {leads[0].score} · {_lead_line(leads[0])[0]}"
    muted = set((org.settings or {}).get("digest_muted", []))
    sent = 0
    for user in org_recipients(session, org):
        if user.id in muted:
            continue
        off = digest_off_url(org.id, user.id)
        footer = f"<a href='{html.escape(off)}' style='color:#E2B25A'>Stop Morning Drop emails</a>"
        try:
            send_email(user.email, subject, "\n".join(rows_text) + f"\n\n--\nStop these emails: {off}\n",
                       wrap_html("Your Morning Drop", body, "Open Pegasus", f"{base}/app", footer, preview=preview),
                       headers={"List-Unsubscribe": f"<{off}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        except Exception:  # noqa: BLE001 - one bad address must not stop the rest of the team's drop
            log.exception("morning drop to %s failed", user.email)
            continue
        sent += 1
    return sent


def digest_off_url(org_id: int, user_id: int) -> str:
    return f"{get_settings().public_url}/email/morning-drop/off?t={make_token(DIGEST_OFF, {'o': org_id, 'u': user_id})}"


def read_digest_off_token(token: str) -> tuple[int, int] | None:
    data = read_token(DIGEST_OFF, token, max_age=60 * 60 * 24 * 365 * 3) if token else None
    return (data["o"], data["u"]) if data else None


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
