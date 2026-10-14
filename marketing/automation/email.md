# Email delivery

## Transactional and lifecycle (required)

Pegasus sends sign-in links, invites, the Morning Drop and lifecycle sequences over SMTP. Any provider works:

| Provider | Cost | Notes |
|---|---|---|
| Amazon SES | $0.10 per 1,000 | Cheapest. Request production access, verify the domain |
| Postmark | from $15/mo | Best deliverability for transactional |
| Zoho / Google Workspace | mailbox price | Fine for low volume; daily sending caps apply |

`.env`:

```
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
MAIL_FROM=Pegasus <hello@getpegasus.org>
```

DNS for the sending domain: **SPF**, **DKIM** (from the provider) and **DMARC** (`v=DMARC1; p=none; rua=mailto:dmarc@yourdomain`, tightened to `quarantine` after two clean weeks). Gmail and Yahoo require all three plus one-click unsubscribe, which Pegasus already adds.

Without `SMTP_HOST`, emails are logged and not sent. That's handy for local development.

## Broadcasts: Listmonk (optional, free)

Use it for the launch blast and the weekly newsletter. It runs in Docker next to Pegasus:

```bash
mkdir -p /opt/listmonk && cd /opt/listmonk
curl -LO https://github.com/knadh/listmonk/raw/master/docker-compose.yml
docker compose up -d            # then open http://SERVER:9000 and create the admin user
```

Point Listmonk's SMTP settings at the same provider. Put it behind Caddy on a subdomain (e.g. `lists.getpegasus.org`).

Weekly newsletter ("Hot permits in {city}"):

1. Monday: `pegasus marketing weekly-posts` writes one post per city to `marketing/dist/weekly/`.
2. In Listmonk, duplicate last week's campaign, paste the new caption and slides, pick the city's list and schedule it for Tuesday at 7:00.

Lists to create: `Waitlist`, `Newsletter – {city}` (one per launch city), `Customers` (for product updates; import from Mission Control's CSV).
