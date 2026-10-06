# Blackwell Lead Engine: Build Plan

## Goal
One dashboard that finds construction leads in **Hampton Roads, VA** for decks, garage and house framing, new construction, additions, and kitchen and bath remodels. It covers both **homeowners** (direct work) and **builders/GCs** (framing subcontract work).

**Constraint:** it runs on your own VPS using only free tools. No paid APIs, no hosted database, no subscriptions.

## Stack (all free, self-hosted)
| Need | Choice |
|---|---|
| App + dashboard | Python 3.11+, FastAPI, server-rendered Jinja pages (no JS build step) |
| Database | SQLite (one file, WAL mode). Works with Postgres via `DATABASE_URL` if ever needed |
| Scheduler | APScheduler `worker` process (imports at 6:05 & 14:05, digest at 7:30) |
| Browser scraping | Playwright + headless Chromium (optional image build, for Accela portals) |
| Classification | Keyword + permit-field rules; optional local LLM via **Ollama** |
| Map | Leaflet (bundled in the repo) + OpenStreetMap tiles |
| Geocoding | US Census Bureau geocoder (free, no key, cached) |
| Email digest | Any SMTP, e.g. a Gmail app password |
| Phone alerts | ntfy (free app / free server) |
| HTTPS | Caddy + Let's Encrypt |
| Deploy | Docker Compose (web, worker, caddy, optional ollama) or systemd |

## Lead sources
| Kind | Source | Adapter | State |
|---|---|---|---|
| Permits | Norfolk: `data.norfolk.gov` dataset `fahm-yuh4` | `socrata` | enabled |
| Permits | Virginia Beach: `Building_Permits_Applications_view` FeatureServer | `arcgis` | enabled |
| Permits | Chesapeake: eBUILD (`aca-prod.accela.com/CHESAPEAKE`) | `accela` | needs browser image |
| Permits | Suffolk, Portsmouth, Hampton, Newport News… | `accela` / `socrata` / `arcgis` | add per city with `inspect` |
| Bids | CivicPlus bid RSS (Norfolk, Hampton, Suffolk) | `rss` | verify, then enable |
| Bids | eVA and other bid pages | `html_list` (CSS selectors) | template |
| Homeowner requests | Gmail label: Craigslist alerts, Angi/Thumbtack, web form, FB/Nextdoor notifications | `imap` | needs app password |
| Homeowner requests | Referrals, calls, social posts | Quick Add form | done |
| New subdivisions | Planning commission agenda PDFs | `agenda_pdf` | template |

No scraping of Facebook, Nextdoor or Craigslist pages (their terms forbid it). Their email alerts go through the inbox instead.

## Data model
`sources` (run health) · `raw_records` (untouched payloads, unique per source+id) · `leads` (normalized, classified, scored, status) · `activities` (notes, calls, quotes, status changes) · `geocode_cache`.

## Classification and scoring
- **Job types:** new_construction, house_framing, garage_framing, addition, deck, kitchen, bath, remodel. Trade-only work (electrical, HVAC, plumbing, roofing, solar, fences, pools, signs, demolition) is dropped unless the description names our work.
- **Customer:** bid → public; subdivision → builder; request → homeowner; permit with a named contractor, new home or commercial → builder; otherwise homeowner.
- **Score 0–100:** job type (≤30) + value (≤25) + recency (≤20) + distance from base (≤15) + bonuses (owner-pulled permit, active request, open bid), minus a commercial penalty. Expired bids score 0.
- **Dedupe:** normalized street address + job type within 90 days across sources.
- User edits (status, job type, contact info) are never overwritten by re-imports.

## Phases
- [x] **Phase 0: Recon.** Norfolk Socrata and VB ArcGIS endpoints identified; Chesapeake Accela confirmed.
- [x] **Phase 1: MVP.** Package, schema, Norfolk + VB adapters, rule classifier, lead feed with filters and status.
- [x] **Phase 2: Smarts.** Scoring, dedupe, Census geocoding, map, lead detail, notes, optional Ollama fallback.
- [x] **Phase 3: Coverage.** Accela adapter, RSS and HTML bid adapters, Bids, Builders and Sources pages.
- [x] **Phase 4: Workflow.** Pipeline board, email digest, ntfy hot-lead pushes, Quick Add, CSV export.
- [x] **Phase 5: Expansion.** IMAP homeowner-request intake, planning-agenda subdivision watcher.
- [ ] **Phase 5b: Go-live on the VPS.** Run `leadengine inspect` on each source against live data, fix `fields:` mappings, enable bids/Chesapeake/agendas.
- [ ] **Phase 6: Enrichment (optional).** Owner name and mailing address from city assessor/GIS parcel data, contractor license status from the Virginia DPOR lookup, more cities.

## Verification
- `pytest`: 57 offline tests with recorded fixtures for every adapter (Socrata, ArcGIS, Accela grid, RSS, HTML list, agenda text, email), classifier cases, scoring, idempotent re-runs, cross-source dedupe, preserved user edits, a failing source, every dashboard page, CSRF and login.
- `leadengine run --dry-run`: fetch and classify against live sources without saving.
- `leadengine inspect <source>`: check a live feed's columns and classification before enabling it.
