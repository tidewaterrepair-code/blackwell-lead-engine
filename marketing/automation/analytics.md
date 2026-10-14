# Analytics

| Question | Where to look |
|---|---|
| Which channel brings signups and paying customers? | Mission Control → Signups by source (UTM captured at signup and on the waitlist) |
| MRR, trials, churn, founding seats | Mission Control |
| Site traffic, top pages, referrers | Umami (optional, below) |
| Ad spend vs results | Meta Ads Manager and Google Ads, using the UTM links from `dist/ads/utm_links.csv` |

## Umami (privacy-friendly site analytics, free, self-hosted)

```bash
mkdir -p /opt/umami && cd /opt/umami
curl -LO https://raw.githubusercontent.com/umami-software/umami/master/docker-compose.yml
docker compose up -d   # http://SERVER:3000, default login admin / umami, change it immediately
```

Add the website in Umami, then set in Pegasus `.env`:

```
UMAMI_SRC=https://stats.getpegasus.org/script.js
UMAMI_WEBSITE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The tag is added to every marketing page. The app itself (`/app`) tracks product events internally (signups, swipes, contacts, wins) in the `events` table.

## Ad conversion tracking

- **Meta**: create a Pixel and add it to Umami's events, or use Meta's Conversions API through Zapier: Pegasus signup webhook → Meta CAPI "Lead".
- **Google Ads**: import the "signup" goal from GA4, or upload offline conversions weekly using `gclid` (saved with each signup's UTM data when the visitor came from an ad).

## Weekly KPIs (see `launch/plan.md` §7)

Waitlist adds, trial starts, trial→paid %, CAC by channel, MRR, logo churn, and the share of users opening the app 3+ days a week.
