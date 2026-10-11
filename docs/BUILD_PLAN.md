# Pegasus: build plan and status

Pegasus grew out of the single-user Blackwell Lead Engine (a Hampton Roads construction lead finder) and is now a multi-tenant SaaS for any trade and for real estate agents and investors. This page records what was planned, what was built and where the build differs from the plan.

## Decisions

| Question | Decision |
|---|---|
| Market | Customers pick their own area anywhere in the US. Source Scout builds connectors for new areas |
| Data spend | Pay as you grow. Paid data (skip trace, parcels) is resold as credits. Agents connect their own MLS feed |
| Hosting | Your VPS, Python kept |
| Brand | Pegasus · data & lead technology |
| Launch ad budget | $500–1,500/month |

## Architecture as built

| Layer | Built with | Note vs. original plan |
|---|---|---|
| API and site | FastAPI, Jinja (marketing site), JSON API | as planned |
| App | React 18, Vite, TypeScript, Tailwind, Framer Motion, Leaflet; served at `/app` | as planned |
| Database | Postgres 16 (SQLite for dev/tests), SQLAlchemy 2, Alembic | **No PostGIS**: territory matching (radius, polygon, ZIP, county, city) runs in Python on indexed lat/lng and FIPS. Add PostGIS when one metro passes about 1M signals |
| Jobs | DB-backed queue (atomic claim) + APScheduler worker | **No Redis/Arq**: one less service; scale by running more worker replicas |
| AI | Claude API (models set in `.env`), server-side fallback, structured JSON output; Ollama or templates without a key | Model choice moved to config instead of being fixed per task |
| Learning | Bayesian updates of timeline and likely-to-sell weights from won/lost outcomes, nightly | **Instead of LightGBM**: works from the first few dozen outcomes. Swap in gradient boosting once there are thousands |
| Billing | Stripe Checkout, Portal, webhooks (idempotent) | as planned |
| Email | SMTP (any provider) for transactional and lifecycle; Listmonk for broadcasts | as planned |
| Edge | Caddy (automatic HTTPS) | as planned |

## Phases

| # | Phase | Status |
|---|---|---|
| 1 | Foundation: rename to `pegasus`, accounts (password + magic link), orgs, teams, invites, territories, shared signals → private `org_leads`, job queue | done |
| 2 | Trades engine: taxonomy and 25 trade profiles, classifier, scoring, predicted "next job" timelines, storm/deed/code-violation adapters | done |
| 3 | Real estate: properties, distress stack, motivation score, likely-to-sell, deal analyzer, farm stats and market reports, skip trace with DNC/litigator flags, RESO MLS sync + CSV import, expired-listing leads | done |
| 4 | Billing: plans, trial, plan limits, credits, add-ons, exclusive ZIPs, founding pricing, referral commissions | done |
| 5 | Source Scout (discover → probe → map → validate → approve) and Mission Control | done |
| 6 | App UI: design system, Lead Stream with swipe, radar map, pipeline, deals, areas, gamification, recap, onboarding, installable web-app manifest | done |
| 7 | Marketing site, SEO pages, launch toolkit, lifecycle email | done |
| 8 | Deploy: Docker image, compose stack, migrations, backups, docs | done |
| 9 | Learning loop at scale: calibration reports, gradient-boosted models once outcome volume allows | ongoing |

## Verification done

- 116 automated tests pass on both SQLite and Postgres 16. They cover tenancy isolation, adapters on recorded fixtures, classification, predictions, billing webhooks, credits, Scout, real estate, MLS, the site, the toolkit, lifecycle email, and migrations matching the models.
- The production Docker stack was built and run: migrations, two web workers, the worker, the backup job, Caddy HTTPS and the live event stream through the proxy.
- UI screenshots were checked at phone and desktop sizes in light and dark mode. Rendered banners and emails were checked visually.

## Before launch

1. **Live data check on the VPS.** City open-data hosts were blocked in the build sandbox, so the adapters were built against recorded and documented responses. Run `pegasus inspect` on each Hampton Roads source and enable the ones that look right.
2. **Attorney review** of the Terms, Privacy, Acceptable Use and Data Sources drafts. Also confirm TCPA, CAN-SPAM and Virginia rules for your outreach features.
3. **Stripe** products, coupon and webhook (`marketing/automation/stripe.md`), tested end to end with a test card.
4. **MLS**: apply for data licenses with the vendor that serves your local MLS (e.g. REIN in Hampton Roads) before advertising MLS connect.
5. **Ad import templates**: Meta and Google change bulk-import columns from time to time. Compare `dist/ads/*.csv` with a freshly downloaded template before the first import.
6. **Beta**: invite 10–20 founding members and watch Mission Control (trial activity, sources, Scout queue) daily for two weeks.
