# Pegasus launch toolkit

Everything needed to launch and market Pegasus. Copy and data live in plain files, and the `pegasus marketing` command turns them into finished assets. Edit a file, re-run, and every asset updates.

| Folder | What's in it | How it's used |
|---|---|---|
| `launch/plan.md` | Positioning, audiences, offer, week-by-week timeline, budget splits for $500, $1,000 and $1,500 a month, KPIs | Read first |
| `brand/` | Brand guide (colors, type, voice) and SVG logos | Profile pictures, headers, decks |
| `content/calendar.csv` | 30 days × 3 posts (90 captions) for both audiences, with hooks, hashtags, CTAs, asset references and UTM tags | Scheduler import (see `automation/social.md`) |
| `video/` | 12 video scripts (15/30/60s): shot lists, voiceover, on-screen text and text-to-video prompts | Film them yourself, or generate them with an AI video tool |
| `ads/campaigns.yaml` | Meta and Google campaigns, ad sets, audiences, keywords, negatives, headlines | `pegasus marketing ads` → import files |
| `banners/copy.yaml` | Banner copy, layouts, map pins, lead cards and sizes | `pegasus marketing render` → PNGs |
| `banners/plates/` | Photo backgrounds for the banners, plus the AI prompt for each | Drop in `<plate>.jpg`; until then a code-drawn night city is used |
| `email/` | How lifecycle email works; copy lives in `pegasus/marketing/emails/*.yaml` | Sent automatically by the worker |
| `automation/` | Runbooks for Stripe, email, social scheduling, analytics and the weekly routine | Setup |
| `dist/` | Generated output (git-ignored) | Upload or import |

## Commands

```bash
pegasus marketing brand         # logo kit: emblem, wordmarks, app icon, favicons, email header (from pegasus/marketing/brand.py)
pegasus marketing render        # banners: 13 designs × 7 sizes + the social share image → dist/banners/*.png
pegasus marketing ads           # dist/ads/meta_bulk.csv, google_ads_editor.csv, utm_links.csv (validates char limits)
pegasus marketing calendar      # checks the 30-day calendar (coverage, X length limits)
pegasus marketing weekly-posts  # "This week in {city}" posts from live data → dist/weekly/*.md + .json
pegasus marketing emails        # HTML previews of all 20 emails + waitlist_listmonk.csv → dist/email/
pegasus marketing all           # all of the above
```

Options: `--out DIR` (default `marketing/dist`), `--city "Virginia Beach" --state VA` for weekly posts.

Banner rendering needs Chromium: `pip install playwright && playwright install chromium`, or point `CHROMIUM_PATH` at an existing Chrome/Chromium binary. Weekly posts are polished by Claude when `ANTHROPIC_API_KEY` is set; otherwise the template copy is used as is.

## What runs by itself once deployed

- **Lifecycle email** (worker, daily): waitlist nurture (5), onboarding (7), trial-to-paid (4) and win-back (3). Each email goes once, honors unsubscribes and carries a one-click unsubscribe header. Details in `email/README.md`.
- **SEO pages**: `/leads`, `/leads/{state}/{city}` and `/leads/{state}/{city}/{job}` refresh from live data on every request and are listed in `/sitemap.xml`.
- **Referrals**: `/r/{code}` links, 30% recurring commission recorded from Stripe invoices.
- **Share-to-earn**: the weekly recap card in the app awards credits when shared.
- **Mission Control** (`/app/admin`): MRR, trials, signups by UTM source, coverage and the Source Scout queue.

## What you do by hand (once)

1. Create Stripe products and prices: `automation/stripe.md`.
2. Connect SMTP (Amazon SES, Postmark, Zoho…) and optionally Listmonk: `automation/email.md`.
3. Install Postiz or set up the Zapier recipe for social posting: `automation/social.md`.
4. Import the ad files into Meta Ads Manager and Google Ads Editor. Campaigns import **paused**, so review them, attach the rendered creatives and switch them on.
5. Follow `automation/weekly-routine.md` every Monday (about 30 minutes).

## Ground rules baked into the copy

- No invented testimonials, customer counts or results. Add real ones as they come in.
- Founding seats left is always the live number from the database.
- Contractor and agent claims stick to what the product does. Likely-to-sell never uses protected-class data, and contact data is DNC-flagged.
