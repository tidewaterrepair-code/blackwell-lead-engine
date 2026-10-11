# Launch week · Oct 12–18, 2026

**Big idea:** *Opportunity finds you.* Every job in your town is on file before it's posted, and Pegasus gets you there first.
**Offer all week:** 14 days free, no card · founding members (first 100) keep 40% off for life.
**Goal:** 10+ founding seats, trial cost under $25, 3 UGC creators signed.

| Day | Theme | Hero post | Supporting |
|---|---|---|---|
| Mon 10/12 | **Launch** | Commercial (Reel/TikTok/Shorts) | Story, founder LinkedIn post (boost), X, Google Business Profile |
| Tue 10/13 | **Contractors: filed before it's posted** | 5-slide carousel | UGC #1 "My 7am", X timeline post, Facebook group value post |
| Wed 10/14 | **Agents: 5 public signs a home will sell** | 6-slide carousel | UGC #3 "Expired at midnight", X, LinkedIn question post |
| Thu 10/15 | **Prediction + storms** | "One permit, 14 trades" reel | Story, roofer storm post, X |
| Fri 10/16 | **Cost of waiting + founding seats** | 4-slide carousel | UGC #5 "Shared leads vs public record", X founding post |
| Sat 10/17 | **Founder story** | Founder video (all platforms) | Founding-seats story |
| Sun 10/18 | **This week in your city (live data)** | `pegasus marketing weekly-posts` | City-page story |

## What's in this folder

| File | What it is |
|---|---|
| `ads.md` | The 30 s commercial (shot list, VO, supers, music, AI shot prompts), 15 s and 6 s cutdowns, this week's Meta ads, Google additions, LinkedIn and YouTube plan, budget split |
| `ugc.md` | Creator brief, six UGC scripts with three hooks each, founder-led videos, FTC disclosure rules, filming checklist |
| `posts.md` | All 25 social posts for the week: time, platform, asset, caption, hashtags, tracked link |
| `schedule.csv` | The same posts as an import file for Postiz or Buffer |
| `creative.yaml` | Copy for the week's 6 ad concepts, 3 carousels and 3 stories (51 images across sizes) |
| `build_schedule.py` | Source of the posts; edit it and run it to regenerate `schedule.csv` and `posts.md` |

Render the images: `pegasus marketing week --week 2026-10-12` → `marketing/dist/weeks/2026-10-12/`.
Export the ads (now including the W42 ads): `pegasus marketing ads` → `marketing/dist/ads/`.

## Budget this week ($1,000/month tier ≈ $233/week)

Meta $130 · Google Search $70 · LinkedIn boost $40 (counts against next week's slack) · YouTube bumpers $25 test (optional). Creators: budget $300–$1,200 for 2–3 micro-creators (one-time, with 90-day usage rights).

## Your to-do list

**Before Monday 7am**
- [ ] Import `schedule.csv` into Postiz/Buffer, or set reminders.
- [ ] Upload the Meta ads (`pegasus marketing ads` → `meta_bulk.csv`), attach images from `dist/weeks/2026-10-12/`, and switch them on.
- [ ] Decide how to make the commercial (see "AI video" below). If it isn't ready Monday, post the founder video (UGC Script 6) in its slot and run the commercial from Wednesday.
- [ ] DM 10 local contractors and agents who post video and send them the creator brief in `ugc.md`. Give each a free account.

**During the week**
- [ ] Film the "One permit, 14 trades" screen video (Thu) and your founder story (Sat).
- [ ] Reply to every comment within 2 hours; turn good questions into 15 s reply videos.
- [ ] Friday: move 60% of Meta contractor spend to the best ad by cost per trial.

**Sunday**
- [ ] On the server: `pegasus marketing weekly-posts`, then post `dist/weekly/<city>.md` with real numbers.
- [ ] Note the numbers in Mission Control: trials, founding seats, cost per trial by UTM source.

## AI video (needs your OK: it spends credits)

The commercial has 6 AI-able shots of 5 s each (shot 3 is a screen recording). Current balances: **OpenArt 40 credits, Higgsfield 10 credits**. Neither covers a video yet. Per-shot prices (OpenArt, default settings, quoted Oct 11; prices change, so I'll re-quote before generating):

| Model | Per 5 s shot | 6 shots |
|---|---|---|
| PixVerse V6, 540p | 50 credits | 300 credits (draft quality) |
| Veo 3.1, 1080p, 4 s, with audio | 120 credits | 720 credits |
| Kling 3.0, standard, 5 s, with sound | 175 credits | 1,050 credits |

Recommended: drafts on PixVerse, then the two hero shots (pins rising over the neighborhood, Pegasus logo reveal) on Veo or Kling. That's about 300 + 2×120 = **540 credits**. Add credits at https://openart.ai/pricing?utm_source=mcp, then tell me to generate and I'll re-check prices first.
The cheaper alternative is filming shots 1, 4, 5 and 6 yourself on a phone at golden hour; then only shots 2 and 7 need AI (about 240 credits on Veo).

## Ground rules used in every asset

- Numbers are either live data, the visitor's own inputs, or clearly labeled examples ("Example: $12,000 job…").
- No testimonials, ratings or customer counts until they're real.
- UGC comes from real people with `#ad` disclosure; AI is never presented as a customer.
- Real estate copy talks about properties, never about people's circumstances or protected characteristics.
