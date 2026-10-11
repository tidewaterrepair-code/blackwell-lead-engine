# Pegasus · data & lead technology

Pegasus is a subscription lead-intelligence app for **contractors of any trade** and for **real estate agents and investors**. Every morning it reads the public record in each customer's area: building permits, bids, plats, property sales, storm reports, tax and court filings, and (for agents) their own MLS feed. It ranks what matters for that customer, predicts the jobs and sellers that come next, and delivers them in a fast, game-like app.

It's self-hosted on one VPS: Python (FastAPI) and Postgres, with a React front end served by the same app.

## What customers get

| | Trades (24 trades from framers to pool builders, plus suppliers) | Realty (agents, wholesalers, investors) |
|---|---|---|
| **Leads** | New permits, bids, subdivisions and storm swaths, scored for their trade | Distress stack: tax liens, pre-foreclosure, probate, code violations, absentee owners, long ownership with high equity |
| **Prediction** | "Next job" timelines: one new-home permit → when framing, roofing, HVAC, flooring, deck and fence get hired | Likely-to-sell probability from property facts only (no protected-class data) |
| **Tools** | Pipeline, notes, follow-ups, team seats, CSV export, AI "why this lead" briefs | Deal analyzer (comps ARV, repairs, 70% MAO, grade), farm heat map, branded market reports, MLS connect (expired/withdrawn listings) |
| **Contact** | DNC- and litigator-flagged skip trace, paid with credits | same |

Plus: any US area (radius, ZIPs, counties, cities or a drawn shape), exclusive ZIPs, the 7am **Morning Drop**, live radar map, swipe-to-save Lead Stream, XP, streaks, badges, a shareable weekly recap, and push alerts.

**Nationwide coverage.** When a customer picks an area Pegasus doesn't cover yet, **Source Scout** searches open-data catalogs (Socrata, ArcGIS Hub) and the web, probes candidate datasets, maps their fields into a declarative connector config (never generated code), validates it on live samples, and queues it for one-click approval in Mission Control. It auto-approves above a confidence threshold.

## Pricing (built in)

| Plan | Monthly | For |
|---|---|---|
| Scout | free | 1 trade, small area, 15 leads/mo shown 7 days late |
| Pro | $79 | Solo pro: 1 trade or Realty, 1 territory, real-time |
| Growth | $179 | 3 trades, 3 territories, 5 seats, predictions, deal tools (the 14-day trial plan) |
| Agent Elite | $249 | MLS connect, farm reports, 400 credits |
| Team | $799 | Brokerages, builders, supply houses |

Add-ons: credits ($0.25 per skip trace), extra territory $29/mo, exclusive ZIP $149/mo. Annual billing gets 2 months free. The first 100 accounts get **founding pricing (40% off for life)**, and referrals earn **30% recurring**. Plans are defined in [`pegasus/plans.py`](pegasus/plans.py).

## Run it locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
(cd frontend && npm ci && npm run build)   # builds the app into pegasus/web/static/app
pegasus demo                               # demo data + accounts (password: pegasus-demo)
pegasus serve                              # http://localhost:8000
pegasus worker                             # in a second terminal: schedule + background jobs
```

Demo logins: `demo@pegasus.test` (trades), `agent@pegasus.test` (realty), `boss@pegasus.test` (Mission Control). Use SQLite locally. No keys are needed: AI, Stripe, email and data providers each switch on when their key is set.

For front-end development, run `cd frontend && npm run dev` (Vite at :5173, proxying the API).

## Deploy

One VPS (4 vCPU / 8 GB is comfortable for hundreds of customers) with Docker:

```bash
cp .env.example .env     # domain, SECRET_KEY, POSTGRES_PASSWORD, admin email
docker compose up -d --build
```

The stack includes Postgres 16, the web app (it applies migrations on start), the worker, Caddy (automatic HTTPS) and nightly backups. Full guide: **[docs/DEPLOY.md](docs/DEPLOY.md)**.

## Launch and marketing

[`marketing/`](marketing/README.md) has the launch plan, brand kit, 90-post content calendar, 12 AI-ready video scripts, Meta and Google campaigns, banner copy and automation runbooks. `pegasus marketing all` renders 50 banner PNGs, exports ad import files, builds weekly data-driven posts and previews every email. Lifecycle email (waitlist, onboarding, trial-to-paid, win-back) is sent automatically by the worker.

## Command line

```
pegasus serve | worker                 web app / background worker
pegasus db upgrade | stamp | current   migrations (stamp = adopt a database created before migrations)
pegasus db revision -m "..."           new migration after changing pegasus/models.py
pegasus run [SOURCE ...]               ingest now
pegasus inspect SOURCE                 raw records → how they normalize and classify
pegasus sources                        source health
pegasus scout FIPS                     Source Scout for a county (e.g. 51810)
pegasus approve SOURCE                 approve a proposed source
pegasus classify "TEXT"                test the classifier
pegasus make-admin EMAIL               Mission Control access
pegasus daily                          run the daily job now
pegasus demo                           seed demo data (never in production)
pegasus marketing render|ads|calendar|weekly-posts|emails|all
```

## Code map

| Path | What |
|---|---|
| `pegasus/models.py` | Tables. Shared `signals` and `properties`; private per-customer `org_leads`; territories, billing, MLS, Scout |
| `pegasus/ingest.py` | fetch → normalize → classify → dedupe → enrich → predict → fan out to matching territories → score |
| `pegasus/sources/` | Adapters: Socrata, ArcGIS, Accela (browser), RSS/HTML, agenda PDFs, IMAP inbox, NOAA storms, CSV/XLSX |
| `pegasus/intel/` | Taxonomy and trade packs (`data/*.yaml`), classifier, scoring, timeline predictions, learning loop, Claude calls |
| `pegasus/realestate/` | Properties and distress, likely-to-sell, deal analyzer, farm stats, skip trace, RESO MLS sync |
| `pegasus/scout/` | Source Scout: discover, probe, map, validate |
| `pegasus/billing.py`, `plans.py` | Stripe checkout, portal and webhooks; credits, limits, referrals |
| `pegasus/api/` | JSON API for the app and Mission Control |
| `pegasus/web/` | App factory, marketing site, SEO pages, templates |
| `pegasus/lifecycle.py` | Lifecycle email sequences |
| `pegasus/migrations/` | Alembic migrations |
| `frontend/` | React + Vite + Tailwind + Framer Motion app |
| `marketing/` | Launch toolkit |
| `sources.yaml` | Seed sources (Hampton Roads); Scout adds the rest in the database |

## Tests

```bash
pytest                                                              # SQLite
PEGASUS_TEST_DATABASE_URL=postgresql://user@host/pegasus_test pytest   # same suite on Postgres (wipes that DB)
```

The suite covers tenancy isolation, classification, scoring, predictions, every adapter (recorded fixtures), billing webhooks, credits, Source Scout, real estate, MLS, the marketing site, the launch toolkit and lifecycle email. A migration test fails if a model changes without a migration.

## Compliance notes

- Public data only, fetched politely and within each site's terms. MLS data comes only through the agent's licensed RESO Web API vendor or their own export, is visible only to that agent, and is never scraped through an MLS login.
- Phones are flagged against DNC and litigator lists, and outreach needs consent. Pegasus is not a consumer reporting agency (no FCRA uses). Likely-to-sell excludes protected classes.
- Opt-out at `/optout`, email unsubscribe on every marketing email.
- Terms, privacy, acceptable use and data-source pages ship as **drafts for an attorney to review** before launch.
