# Blackwell Lead Engine

A self-hosted construction lead finder for **Hampton Roads, VA**. It pulls new building permits, public bids, homeowner requests and planning-agenda subdivisions, then sorts them into:

**Decks / porches · Garages · House framing · New construction · Additions · Kitchen remodels · Bath remodels** (plus "other remodel").

Every lead gets a 0–100 score from job type, value, how recent it is, and distance from your shop. You can work leads from your phone through **New → Contacted → Quoted → Won / Lost**.

All of it is free: Python, SQLite, OpenStreetMap, the US Census geocoder, Gmail SMTP and ntfy push. There are no paid APIs and no accounts to sign up for. It runs on any small VPS (1 GB RAM is plenty).

## What's in the dashboard

| Page | What it's for |
|---|---|
| **Leads** | Best-first feed with filters (job type, homeowner vs. builder, city, date, status), search, and CSV export |
| **Map** | Pins colored and lettered by job type, around your home base |
| **Pipeline** | Columns for Contacted, Quoted, Won and Lost, plus a won-$ total |
| **Bids** | Open public bids/RFPs, soonest deadline first |
| **Builders** | GCs ranked by new-home permits. These are your framing-sub prospects |
| **+ Add** | Quick entry for referrals, Facebook/Nextdoor posts, phone calls |
| **Sources** | Health of each import, a "run now" button, and error details |

Plus a **daily email digest** of the best new leads and **instant phone pushes** for hot ones (score ≥ 80).

## Lead sources

| Source | Kind | Status |
|---|---|---|
| Norfolk permits: data.norfolk.gov (Socrata API) | permit | **on** |
| Virginia Beach permit applications: city ArcGIS open data | permit | **on** |
| Chesapeake eBUILD (Accela portal, headless browser) | permit | off until you build with the browser |
| City bid postings (CivicPlus RSS: Norfolk, Hampton, Suffolk) | bid | off until checked with `inspect` |
| eVA / any bid web page (`html_list` with CSS selectors) | bid | template in `sources.yaml` |
| Gmail label of lead emails (Craigslist alerts, Angi/Thumbtack, website form) | homeowner request | off until IMAP is set |
| Planning commission agenda PDFs (subdivisions, rezonings, plats) | subdivision | template in `sources.yaml` |

Every source is one block in [`sources.yaml`](sources.yaml). To add another city, copy a block, then run `leadengine inspect <id>` to check it.

## Quick start on a VPS (Docker)

```bash
git clone https://github.com/tidewaterrepair-code/blackwell-lead-engine.git
cd blackwell-lead-engine
cp .env.example .env && nano .env        # set APP_PASSWORD, SECRET_KEY, DOMAIN, BASE_LAT/LNG
docker compose up -d --build
docker compose exec web leadengine run   # first import now, instead of waiting for 6am
```

Open `https://<your DOMAIN>`. Caddy gets the HTTPS certificate automatically once your domain's DNS points at the VPS. The full walkthrough, including running without Docker, is in [docs/DEPLOY.md](docs/DEPLOY.md).

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                       # 57 tests, offline (recorded fixtures)
.venv/bin/leadengine run               # import from enabled sources
.venv/bin/leadengine serve             # http://localhost:8000
```

## CLI

```
leadengine run [SOURCE ...] [--days N] [--dry-run]   import now
leadengine inspect SOURCE [--days N]                 raw records + how they classify (for setting up a source)
leadengine sources                                   list sources and last run
leadengine classify "Build 12x16 deck"               test the classifier
leadengine digest | rescore | serve | worker
```

## How it works

```
sources.yaml ─► adapter.fetch() ─► raw_records (kept, so data can be re-processed)
                     │
                     ▼
              adapter.normalize() ─► classify (rules → optional local AI) ─► score ─► dedupe ─► leads
                                                                                              │
                         dashboard ◄──────────────────────────────────────────────────────────┤
                         daily email digest / ntfy push ◄─────────────────────────────────────┘
```

- `leadengine/sources/`: one adapter per source type (`socrata`, `arcgis`, `accela`, `rss`, `html_list`, `agenda_pdf`, `imap`)
- `leadengine/classify.py`: keyword and permit-field rules. It throws out trade-only permits such as electrical, HVAC, roofing, fences and pools
- `leadengine/scoring.py`: score and duplicate keys. The same address and job type seen in two sources within 90 days is merged
- `leadengine/llm.py`: optional free local AI ([Ollama](https://ollama.com)) for records the rules can't place
- `leadengine/web/`: FastAPI + server-rendered pages, no JavaScript build step

See [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) for the roadmap.
