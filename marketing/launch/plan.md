# Pegasus launch plan

**Budget:** $500–1,500/month in paid media, plus organic content that runs on autopilot.
**Goal for day 90:** 100 founding members (sold out), 250 paying customers by month 6, and $35k MRR by month 12.

---

## 1. Positioning

**One line:** *Pegasus: see the job before your competition does.*

**What it is:** a lead-intelligence app. It turns public records (permits, bids, sales, storms, tax and court filings) into a ranked, predicted feed of jobs and motivated sellers for one trade in one area. It's delivered every morning.

**Why it wins:**

| Competitor type | What they do | Pegasus difference |
|---|---|---|
| Shared lead sellers (Angi, HomeAdvisor, Thumbtack) | Sell the same homeowner request to 3–5 contractors | Nobody else is calling yet; exclusive ZIPs available |
| Permit data dumps | Raw spreadsheets | Scored, filtered to your trade, *predicted* next jobs, on your phone |
| PropStream / BatchLeads ($99–749/mo) | Investor list-building | Same distress stack, plus likely-to-sell, MLS merge, permits and storms, at lower prices |

**Proof points to repeat everywhere:**
- "One permit → 14 trades, each told at the right moment" (the new-home sequence)
- "Storm hits at 6pm, roofers have the swath by morning"
- "Fair-housing-safe likely-to-sell scores; DNC-flagged contacts"
- "Any US county; if we don't cover it yet, Source Scout maps it"

## 2. Audiences (ICPs)

| Segment | Who | Pain | Hook | Plan |
|---|---|---|---|---|
| **Trades A** | Framers, deck builders, remodelers, roofers (1–15 employees) | Feast-or-famine pipeline, paying for shared leads | "Stop buying the same lead 5 contractors bought" | Pro / Growth |
| **Trades B** | HVAC, plumbing, electrical, solar, pools, fencing, landscaping | Want new-construction and replacement work | "Every new home needs you in week 6" | Pro / Growth |
| **Builders & suppliers** | Lumber yards, supply houses, GCs | Need to know who's building, early | "Every project in your trade area" | Team |
| **Agents** | Producing agents, small teams | Listings inventory, farming | "Know who's selling before they list" | Agent Elite |
| **Investors** | Wholesalers, flippers, landlords | Off-market deals, data cost | "PropStream's stack + predictions, for less" | Growth / Elite |

Launch geography: **Hampton Roads first** (data is live), then expand through Source Scout to 10 metros where waitlist demand clusters.

## 3. Offer

- **14-day Growth trial, no card.**
- **Founding members (first 100):** 40% off for life. A live counter on the site creates urgency.
- **Exclusive ZIPs** ($149/mo): first come, first served, and they sell scarcity.
- **Referral:** 30% recurring for life. Pitch it to coaches, REIA leaders, trade associations and supply houses.
- **Share-to-earn:** sharing the weekly recap card earns 5 credits. This is the organic viral loop.

## 4. Timeline

### Phase A: Pre-launch (weeks −4 to 0): build the waitlist
| Week | Actions |
|---|---|
| −4 | Domain, email (Google Workspace or Zoho), socials claimed (@getpegasus everywhere, or one consistent fallback). Deploy the site + waitlist. Stripe products created. Postiz + Listmonk installed. |
| −4 | Shoot or generate the first 4 videos (scripts 01, 02, 05, 09). Render banners (`pegasus marketing render`). |
| −3 | Start the daily posting calendar (days 1–30). Join 15 Facebook groups (contractors, REI, local trades) and contribute value posts, not pitches. |
| −3 | Launch the **"Hot permits in {city}" free weekly email** as the lead magnet (generated from live data: `pegasus marketing weekly-posts`). |
| −2 | Personal outreach: 50 contractors + 30 agents from local permit data (they're in the data!). Offer founding seats. |
| −2 | Meta ads, phase 1: **$15/day** waitlist campaign (video 01 + 02), Hampton Roads radius. |
| −1 | Partner calls: 3 supply houses, 2 REIAs, 1 builders association. Offer co-branded permit reports + 30% referral. |

### Phase B: Founding beta (weeks 1–4): 100 founding members
- Week 1: invite the waitlist in batches of 25/day (scarcity + onboarding capacity). Personal onboarding call offered to each.
- Daily: answer every in-app message within 2 hours. Collect 3 video testimonials (real customers only, with permission).
- Week 2: fix the top 5 friction points from PostHog funnels.
- Week 3: Google Search ads on, $10/day on high-intent keywords.
- Week 4: case study #1 (real numbers from a real customer, with permission).

### Phase C: Public launch (week 5)
- Launch-day email to the full waitlist (email/launch-blast.md). Founding seats counter at whatever is left.
- Product Hunt + Indie Hackers posts (mostly for backlinks and credibility).
- Post the launch video (script 12) everywhere; pin it.
- Raise Meta budget to the tier you chose (below).

### Phase D: Scale (week 9+)
- Expand to the next metro each month where waitlist demand or Scout coverage is strongest.
- Programmatic SEO: city × trade pages are generated from live data. Submit the sitemap and watch Search Console.
- Double the best-performing ad set every 2 weeks while CAC stays under 2 months of revenue.

## 5. Budget allocation

| Monthly budget | Meta (FB/IG Reels) | Google Search | Retargeting | AI video/graphics tools | Notes |
|---|---|---|---|---|---|
| **$500** | $250 | $150 | $50 | $50 | One metro, 2 ad sets, 4 creatives |
| **$1,000** | $500 | $300 | $100 | $100 | Two metros, test agent vs trades split |
| **$1,500** | $750 | $450 | $150 | $150 | Three metros, add TikTok Spark Ads ($100 from Meta line) |

Rules:
- Kill any creative whose CTR is under 0.8% after 1,500 impressions.
- Kill any ad set with cost per trial over $45 after 10 trials.
- Scale winners 20% every 3 days.

## 6. KPIs and targets

| Stage | Metric | Target |
|---|---|---|
| Traffic → signup | Landing conversion | ≥ 6% (trial), ≥ 12% (waitlist) |
| Signup → activated | Set an area within 10 minutes | ≥ 80% |
| Activated → engaged | Saved or contacted a lead in week 1 | ≥ 55% |
| Trial → paid | Conversion by day 14 | ≥ 18% |
| Retention | Monthly logo churn | ≤ 4% |
| Economics | CAC payback | ≤ 2 months |
| Virality | Recap shares / active org / month | ≥ 0.5 |

**Funnel math at $1,000/mo:**
- $1,000 at ~$2.50 per landing visit ≈ 400 visits.
- 6% become trials ≈ 24 trials.
- 18% of trials convert ≈ 4–5 paid.
- Organic, referrals and SEO add 6–10 more.
- At about $140 average revenue per customer, that's roughly $1.4–2.1k of new MRR per month. Payback is under 1 month.

## 7. Automation map (what runs by itself)

| Job | Tool | Trigger |
|---|---|---|
| Daily social posts | Postiz (self-hosted) fed by `content/calendar.csv` | Scheduled |
| Weekly data posts ("Top 10 permits in VB") | `pegasus marketing weekly-posts`, then Postiz API | Cron, Mondays 6am |
| Waitlist nurture, onboarding, trial, win-back emails | Listmonk sequences, triggered by Pegasus events | Signup / day N / Stripe webhook |
| Morning Drop + hot alerts | Pegasus worker (built in) | 7am daily / every 30 min |
| Ad creative refresh | `pegasus marketing render`, then upload | When copy.yaml changes |
| Ad structure | `pegasus marketing ads`, then bulk import | When campaigns.yaml changes |
| Referral payouts | Pegasus referral ledger, then monthly payout | 1st of the month |
| Founding-seat counter | Live on the site | Real time |
| KPI dashboard | Pegasus Mission Control + Umami + PostHog | Always on |

See `automation/` for setup steps and `README.md` for the full toolkit index.
