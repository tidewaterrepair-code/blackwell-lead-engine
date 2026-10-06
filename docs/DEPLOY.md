# Deploying on your VPS

Any Linux VPS with 1 GB RAM works (2 GB if you turn on the Chesapeake browser scraper, 6 GB+ for the optional local AI). The steps below assume Ubuntu/Debian.

## 1. Point a domain at the server (for HTTPS)

Create a DNS **A record**, e.g. `leads.yourdomain.com` → your VPS IP. No domain? Skip Caddy and use an SSH tunnel instead (see the end of this page).

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out and back in
```

## 3. Get the code and configure it

```bash
git clone https://github.com/tidewaterrepair-code/blackwell-lead-engine.git
cd blackwell-lead-engine
cp .env.example .env
openssl rand -hex 32            # paste the output into SECRET_KEY
nano .env
```

Minimum settings: `APP_PASSWORD`, `SECRET_KEY`, `DOMAIN`, `PUBLIC_URL`, `BASE_LAT`, `BASE_LNG` (your shop; right-click it in Google Maps to copy the coordinates).

## 4. Start it

```bash
docker compose up -d --build
docker compose exec web leadengine run      # first import (last 30 days)
docker compose logs -f worker               # scheduler log
```

Open `https://leads.yourdomain.com` and log in with `APP_PASSWORD`.

From then on the worker imports at **6:05 and 14:05**, rescores and emails the digest at **7:30**, and pushes hot leads right after each import. Change the times with `INGEST_HOURS` and `DIGEST_HOUR`.

## 5. Check and turn on more sources

```bash
docker compose exec web leadengine inspect norfolk-permits
docker compose exec web leadengine inspect norfolk-bids --days 60
```

`inspect` prints raw records, plus how each one normalizes and classifies. If a column is mapped wrong, add a `fields:` override in `sources.yaml`. When the output looks right, set `enabled: true`, then run `docker compose restart web worker`.

### Chesapeake eBUILD (Accela)

This source needs a headless browser in the image:

```bash
echo "INSTALL_BROWSER=true" >> .env
docker compose build && docker compose up -d
docker compose exec web leadengine inspect chesapeake-permits --days 7
```

The same adapter works for any city on Accela Citizen Access. Copy the block in `sources.yaml` and change `base_url`.

### Homeowner requests by email

1. In Gmail, create a label named `Leads` and a filter that applies it to lead emails: Craigslist saved-search alerts ("services wanted"), Angi/Thumbtack/HomeAdvisor, your website's contact form, Facebook group notifications.
2. Turn on 2-step verification, then create an **App password** (Google Account → Security → App passwords).
3. Put the address and app password in `.env` as `IMAP_USER` and `IMAP_PASSWORD`, then set `enabled: true` on `email-requests`.

### New subdivisions (planning agendas)

Find your city's planning commission agenda page (most Hampton Roads cities use a CivicPlus "Agenda Center"). Uncomment the `agenda_pdf` block, set `index` to that page, and set `link_pattern` to match the PDF links. Agenda items that mention subdivisions, plats, rezonings for homes or townhomes become leads.

## Notifications (free)

- **Email digest**: Gmail SMTP with an app password (`SMTP_*`, `DIGEST_TO`).
- **Phone push**: install the free **ntfy** app, subscribe to a hard-to-guess topic such as `blackwell-leads-8f3k2`, and set `NTFY_URL=https://ntfy.sh/blackwell-leads-8f3k2`.

## Optional: free local AI classifier

The rule-based classifier handles most permits. For odd wording, run a small local model:

```bash
docker compose --profile ai up -d
docker compose exec ollama ollama pull llama3.2:3b
echo "OLLAMA_URL=http://ollama:11434" >> .env && docker compose up -d
```

## Backups

All data lives in one SQLite file in the `leads_data` volume:

```bash
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/leads.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose cp web:/data/backup.db ./leads-$(date +%F).db
```

## Updating

```bash
git pull && docker compose up -d --build
```

## Without Docker (systemd)

```bash
sudo useradd -r -m -d /opt/blackwell-lead-engine leadengine
sudo -u leadengine git clone https://github.com/tidewaterrepair-code/blackwell-lead-engine.git /opt/blackwell-lead-engine
cd /opt/blackwell-lead-engine
sudo -u leadengine python3 -m venv .venv
sudo -u leadengine .venv/bin/pip install .
sudo -u leadengine cp .env.example .env    # edit it; add LEADENGINE_DATA_DIR=/opt/blackwell-lead-engine/data
sudo cp deploy/leadengine-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now leadengine-web leadengine-worker
```

Then put Caddy (`sudo apt install caddy`) or nginx in front of `127.0.0.1:8000`.

## No domain? Use an SSH tunnel

Start only the app (`docker compose up -d web worker`). Then on your laptop run `ssh -L 8000:127.0.0.1:8000 you@your-vps` and open http://localhost:8000.
