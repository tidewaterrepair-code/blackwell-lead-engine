# Social scheduling

The 30-day calendar (`content/calendar.csv`) has 90 posts with platform, audience, format, hook, caption, hashtags, CTA, asset and UTM link. Two ways to publish it automatically.

## Option A: Postiz (self-hosted, free)

Postiz schedules to Facebook, Instagram, TikTok, LinkedIn, YouTube, X, Threads and more from one calendar.

1. Install with Docker following the official guide (docs.postiz.com → Installation → Docker Compose). It runs next to Pegasus on the same VPS. Put it behind Caddy on `social.getpegasus.org`.
2. Connect each channel (Postiz walks you through each platform's developer-app setup).
3. Create posts from the calendar: one row per post, attaching the asset named in the `asset` column (`banners/...` from `dist/banners`, `video/...` once the videos are produced).
4. Postiz also has a public API (Settings → API key) if you'd rather script the import. Check its current docs for the post-creation endpoint before automating.

## Option B: Zapier (no server)

1. Upload `calendar.csv` to Google Sheets and add a `date` column (day 1 = your launch date).
2. Zap: **Schedule by Zapier** (every day 8:00) → **Google Sheets: Lookup rows** where `date` = today → **Filter** by platform → **Facebook Pages: Create post**, **LinkedIn: Create share**, **Instagram for Business: Publish photo**. Use Buffer as the action if you want one step for all networks.

## Weekly data posts

`pegasus marketing weekly-posts` makes a caption and carousel slide text per launch city from live data ("This week in Virginia Beach: 47 new projects…"). Render matching graphics by adding the `banner` block from `dist/weekly/{city}.json` to `banners/copy.yaml`, then running `pegasus marketing render`.

## AI video

Each script in `video/scripts/` includes text-to-video prompts per scene. Produce them with an AI video service, or film the UGC-style ones yourself with a phone. The cut-down 15s versions double as Reels and TikTok ads (see `ads/campaigns.yaml`, `video:` references).
