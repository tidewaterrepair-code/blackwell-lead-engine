# Blackwell Lead Engine: Build Plan

## Context
You want one dashboard that finds construction leads in **Hampton Roads, VA** for decks, garage and house framing, new construction, additions, and kitchen and bath remodels. It covers both customer types: **homeowners** (direct remodels and decks) and **builders/GCs** (framing subcontract work). The repo `tidewaterrepair-code/blackwell-lead-engine` is empty apart from a README, so this is a greenfield build.

How it works: scheduled scrapers pull raw records from public sources. Each record is classified into one of your job types, scored, de-duplicated, and shown on a mobile-friendly dashboard where you work leads through a pipeline (New → Contacted → Quoted → Won/Lost).

## Stack (chosen for you)
- **Next.js (App Router) + TypeScript + Tailwind/shadcn UI**, hosted on **Vercel**. It works on your phone in the truck.
- **Supabase**: Postgres database, login (just you, plus a crew login later), and file storage for permit PDFs.
- **Ingestion workers** in TypeScript, in the same repo. They run on a **GitHub Actions cron** (free; Playwright is available for portals that need a browser).
- **Classification**: keyword and permit-code rules first. Records the rules can't place go to the Claude API (`claude-haiku-4-5`, cheap) to label the job type, size, and customer type.
- Map with **MapLibre/Leaflet**. Addresses are geocoded once with the free US Census geocoder.

## Lead sources (Hampton Roads)
| Kind | Source | Access | Phase |
|---|---|---|---|
| Permits | Norfolk: data.norfolk.gov (Socrata) | SODA JSON API | 1 |
| Permits | Virginia Beach: city open-data permits dataset | API (exact dataset ID confirmed in Phase 0) | 1 |
| Permits | Chesapeake: eBUILD (Accela Citizen Access, `aca-prod.accela.com/CHESAPEAKE`) | Playwright scrape of anonymous search | 3 |
| Permits | Suffolk, Portsmouth, Hampton, Newport News, York, James City | Each portal checked in Phase 0 (open data, Accela/EnerGov, or CSV) | 3 |
| Bids/RFPs | eVA (Virginia state and local procurement) | Scrape public solicitations, filtered by construction NIGP codes | 3 |
| Bids/RFPs | City and county procurement pages, school boards | Page scrape or RSS | 3 |
| Homeowner requests | Craigslist Norfolk "gigs/services wanted" | Only if the site's terms allow it, otherwise saved-search email → inbox parser | 5 |
| Homeowner requests | Facebook groups, Nextdoor, word of mouth | No scraping (against their terms). Use a fast **Quick Add** form or share-sheet instead | 5 |
| New subdivisions | Planning commission and City Council agendas (rezonings, subdivision plats), site-plan submittals in eBUILD | PDF agenda parse + keyword match | 5 |

The **Phase 0** recon pins down every URL, dataset ID, and field mapping, and records them in `docs/sources.md` before any scraper is written.

## Data model (Supabase)
- `sources`: id, name, kind (permit/bid/request/subdivision), jurisdiction, last_run_at, status
- `raw_records`: source_id, external_id, payload jsonb, fetched_at. Unique on (source_id, external_id) so re-runs are idempotent
- `leads`: id, raw_record_id, title, description, job_type enum (deck, garage_framing, house_framing, new_construction, addition, kitchen, bath, other), customer_type (homeowner/builder/public), address, city, lat/lng, est_value, owner_name, contractor_name, contractor_license, contact phone/email, posted_at, due_date (bids), score, status, dedupe_key
- `lead_activity`: lead_id, type (note/call/status_change/quote), body, created_at
- `saved_filters`: name, criteria jsonb, notify (bool)

## Repo layout
```
apps/web/                 Next.js dashboard
packages/core/            shared types, job-type classifier, scoring, dedupe
packages/ingest/
  sources/<jurisdiction>-<kind>.ts   one adapter per source: fetch() → normalize()
  run.ts                  runs all adapters, upserts raw_records → leads
supabase/migrations/      SQL schema
.github/workflows/ingest.yml   cron (e.g. 6am and 2pm daily)
docs/sources.md
```
Each source adapter implements one interface, `{ id, fetch(since), normalize(raw): LeadInput[] }`. New cities plug in without touching the rest of the code.

## Classification and scoring
- **Rules** (`packages/core/classify.ts`): permit type codes plus keywords, e.g. "deck", "porch", "addition", "SFD"/"single family dwelling", "detached garage", "kitchen", "bath", "remodel", "alteration". Exclusions drop noise such as electrical-only, HVAC changeouts, roofs, fences, and pools.
- **LLM fallback** for ambiguous text. The output is a strict JSON schema: job_type, customer_type, confidence, one-line summary.
- **Score (0–100)**: job-type match weight + valuation band + recency + distance from your base + customer type + "no contractor listed yet" bonus (the homeowner may still need someone). For builder leads, a GC with many recent new-home permits scores higher, which points to framing opportunities.
- **Dedupe**: normalized address + job type within 90 days, which merges the same project when it shows up in two sources.

## Dashboard features
1. **Lead feed**: table and cards, filterable by job type, city, customer type, score, date, and status, sorted by score.
2. **Map view** with pins colored by job type.
3. **Lead detail**: source link, permit or bid details, owner/contractor, notes, status changes, a call button, and "Mark quoted/won/lost".
4. **Pipeline board** (kanban by status).
5. **Builders tab**: GCs ranked by new-construction permit volume over the last 90 days, the framing prospect list.
6. **Bids tab**: open RFPs with due-date countdowns.
7. **Daily digest**: email (Resend) of new leads scoring 60 or above, plus alerts for saved filters.
8. **Quick Add**: a manual lead entry form for referrals and Facebook/Nextdoor posts.
9. **Source health**: last run, record counts, and errors per source.

## Phases
- **Phase 0, Recon (½ day)**: confirm endpoints and fields for each jurisdiction and write `docs/sources.md`.
- **Phase 1, MVP (first working version)**: scaffold the monorepo, Supabase schema, Norfolk and Virginia Beach permit adapters, rule-based classifier, and a simple lead feed with filters and status. Deploy to Vercel. At this point you have real leads every morning.
- **Phase 2, Smarts**: LLM fallback classifier, scoring, dedupe, geocoding, map view, lead detail, and notes.
- **Phase 3, Coverage**: Chesapeake eBUILD (Playwright), the remaining cities, eVA, and city procurement bids. Adds the Bids tab, Builders tab, and Source health.
- **Phase 4, Workflow**: pipeline board, daily email digest, saved-filter alerts, Quick Add.
- **Phase 5, Expansion**: homeowner-request intake (Craigslist only if its terms allow, plus an email parser) and the subdivision/agenda watcher.
- **Phase 6, Enrichment (optional)**: owner names and mailing addresses from city assessor/GIS parcel data, contractor license status from the Virginia DPOR license lookup, and an export to CSV or your CRM.

## Secrets needed
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY` (Phase 2), `RESEND_API_KEY` (Phase 4). These are stored as GitHub Actions secrets and Vercel env vars, never committed.

## Verification
- Unit tests (Vitest) for the classifier against a fixture set of about 50 real permit descriptions per job type, including exclusions, and for scoring and dedupe.
- Each adapter gets a recorded-fixture test (a saved API response) so normalize() is tested offline.
- `pnpm ingest --source norfolk-permits --dry-run` prints the normalized leads. Running it twice must produce no duplicate rows.
- Run the dashboard locally (`pnpm dev`) and check the feed, filters, and status changes in the browser with Playwright. Then confirm the GitHub Actions cron run fills the database on schedule.

## Ground rules
- Use public data and official APIs first, respect each site's terms and robots.txt, and keep request rates low.
- Contact data is only what's in public records. No scraping of Facebook, Nextdoor, or login-gated sites.
- All work goes on branch `claude/kind-cerf-2xjti5`.
