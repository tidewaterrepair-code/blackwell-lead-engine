# Deploying Pegasus on your VPS

**Server size.** Ubuntu 22.04/24.04 with 2 vCPU / 4 GB handles a beta of about 100 customers. 4 vCPU / 8 GB covers several hundred. Add about 1 GB if you build with the browser (Accela portals, banner rendering), and 4 GB more for the optional local AI.

**What runs.** Postgres 16, the web app (API, React app, marketing site), the background worker (ingest, scoring, alerts, email, Source Scout, MLS sync), Caddy (HTTPS) and a nightly backup job. Everything is defined in `docker-compose.yml`.

## 1. Domain and DNS

Point two **A records** at the VPS IP: the bare domain (`@`, e.g. `pegasusleads.com`) and `www`. Caddy redirects `www` to the bare domain. Caddy gets the HTTPS certificate on first start.

For email deliverability, add the SPF, DKIM and DMARC records from your mail provider now: see `marketing/automation/email.md`.

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # log out and back in
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

## 3. Get the code and configure

```bash
sudo mkdir -p /opt/pegasus && sudo chown $USER /opt/pegasus
git clone -b claude/kind-cerf-2xjti5 https://github.com/tidewaterrepair-code/blackwell-lead-engine.git /opt/pegasus
cd /opt/pegasus
cp .env.example .env
openssl rand -hex 32     # → SECRET_KEY
openssl rand -hex 16     # → POSTGRES_PASSWORD
nano .env
```

Required: `DOMAIN`, `PUBLIC_URL`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_EMAILS`. The app refuses to start in production without a real `SECRET_KEY`.

Each feature switches on when its block in `.env` is filled in:

| Block | Turns on | Guide |
|---|---|---|
| `SMTP_*` | Sign-in links, Morning Drop, lifecycle email | `marketing/automation/email.md` |
| `STRIPE_*` | Paid plans, credits, add-ons, referrals | `marketing/automation/stripe.md` |
| `ANTHROPIC_API_KEY` | AI lead briefs, Source Scout research and mapping, label fallback, weekly-post polish | console.anthropic.com |
| `BATCHDATA_API_KEY` | Skip trace with DNC flags (sold as credits) | batchdata.com |
| `REGRID_TOKEN` | Parcels, owners, vacancy | regrid.com |
| `SOCRATA_APP_TOKEN` | Higher open-data rate limits (free) | any Socrata portal → developer settings |

## 4. Start

```bash
docker compose up -d --build
docker compose ps                  # postgres healthy, web healthy, worker/caddy/backup up
docker compose logs -f web         # migrations, then "Application startup complete"
```

Open `https://YOUR_DOMAIN`. Sign up with an email from `ADMIN_EMAILS` to get **Mission Control** at `/app/admin`, or promote an existing account with `docker compose exec web pegasus make-admin you@example.com`.

First data import (the worker also does this on schedule at `INGEST_HOURS`):

```bash
docker compose exec web pegasus run
docker compose exec web pegasus sources
```

## 5. Coverage and Source Scout

`sources.yaml` seeds Hampton Roads. Every other area is added by Source Scout when a customer requests it, or manually:

```bash
docker compose exec web pegasus scout 51550       # county FIPS (Chesapeake, VA)
```

Proposals show up in Mission Control → Scout for approval. Configs scoring at least `SCOUT_AUTO_APPROVE` (default 0.85) go live automatically. Set it to `1.01` to review everything.

Check a source's raw records and classification:

```bash
docker compose exec web pegasus inspect norfolk-permits
```

Sources that need a headless browser (Accela portals such as Chesapeake eBUILD) need the browser build:

```bash
echo "INSTALL_BROWSER=true" >> .env && docker compose up -d --build
```

## 6. Stripe webhook

In Stripe, add the endpoint `https://YOUR_DOMAIN/api/stripe/webhook` with the events listed in `marketing/automation/stripe.md`, then put the signing secret in `STRIPE_WEBHOOK_SECRET` and run `docker compose up -d`.

## 7. Backups

The `backup` service writes a compressed `pg_dump` to `/opt/pegasus/backups` every 24 hours and keeps the last 14 (`BACKUP_KEEP`). **Copy them off the server.** For example, Backblaze B2 with rclone (about $1/month):

```bash
sudo apt install rclone && rclone config          # add a "b2" remote
crontab -e
# 30 3 * * *  rclone copy /opt/pegasus/backups b2:pegasus-backups --max-age 2d
```

Restore:

```bash
docker compose stop web worker
docker compose exec -T postgres pg_restore -U pegasus -d pegasus --clean --if-exists < backups/pegasus-YYYYMMDD-HHMM.dump
docker compose start web worker
```

## 8. Updating

```bash
cd /opt/pegasus && git pull
docker compose up -d --build       # web applies new migrations before serving
```

To change the schema: edit `pegasus/models.py`, run `pegasus db revision -m "what changed"` against a development Postgres, review the generated file in `pegasus/migrations/versions/`, and commit it. The test suite fails if a model change has no migration.

## 9. Monitoring

- `https://YOUR_DOMAIN/healthz` returns 200 when the app and database are up. Point a free uptime monitor (UptimeRobot, Better Stack) at it.
- Mission Control → Sources shows failing sources. The worker re-checks source health daily and re-scouts broken ones.
- `docker compose logs --since 1h worker` shows the scheduler and job output.

## Optional extras

- **Local AI fallback** (no Anthropic key): `docker compose --profile ai up -d`, then `docker compose exec ollama ollama pull llama3.2:3b` and set `OLLAMA_URL=http://ollama:11434`.
- **Umami analytics, Listmonk, Postiz**: see `marketing/automation/`. Run them as extra compose projects and add a site block for each in `deploy/Caddyfile`.
- **Scaling past one box**: move Postgres to a managed instance (set `DATABASE_URL`), run more `worker` replicas (jobs are claimed atomically), and raise `WEB_WORKERS`.

## Without Docker (systemd)

```bash
sudo apt install python3.12-venv postgresql nodejs npm caddy
sudo -u postgres createuser pegasus -P && sudo -u postgres createdb -O pegasus pegasus
sudo useradd -r -m -d /opt/pegasus pegasus
sudo -u pegasus git clone -b claude/kind-cerf-2xjti5 https://github.com/tidewaterrepair-code/blackwell-lead-engine.git /opt/pegasus
cd /opt/pegasus
sudo -u pegasus sh -c "cd frontend && npm ci && npm run build"
sudo -u pegasus python3 -m venv .venv && sudo -u pegasus .venv/bin/pip install .
sudo -u pegasus cp .env.example .env   # also set DATABASE_URL=postgresql://pegasus:PASS@localhost/pegasus
sudo cp deploy/pegasus-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pegasus-web pegasus-worker
```

Then point Caddy at `127.0.0.1:8000` (see `deploy/Caddyfile`, replacing `web:8000`).

## A database from before migrations

If you ran an early build that created tables without migrations, mark it current once with `pegasus db stamp`. After that, `pegasus db upgrade` works as normal.
