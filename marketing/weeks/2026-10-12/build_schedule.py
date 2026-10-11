"""Source of truth for this week's social posts. Writes schedule.csv (Postiz/Buffer/Meta import) and posts.md.

    python marketing/weeks/2026-10-12/build_schedule.py
"""

import csv
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).parent
SITE = "https://pegasusleads.com"


def link(path: str, source: str, content: str) -> str:
    return f"{SITE}{path}?{urlencode({'utm_source': source, 'utm_medium': 'social', 'utm_campaign': 'w42_launch', 'utm_content': content})}"


# (day, date, time ET, platform, format, asset, caption, hashtags, link path, content id)
POSTS = [
    # ---------------------------------------------------------------- MON 10/12 · Launch: "Opportunity finds you"
    ("Mon", "2026-10-12", "07:00", "Instagram+Facebook", "Reel", "Commercial 30 s (9:16) or Script 6 founder video",
     "Every morning, someone in your town makes the first call.\n\nPermits, bids, sales and storms are on file before a job is ever posted. Pegasus reads them every morning, ranks them for your trade and tells you what's coming next.\n\nPegasus is live. 14 days free, no card. First 100 keep 40% off for life.",
     "#contractor #construction #realestate #leadgeneration #smallbusiness #hamptonroads", "/", "mon_commercial"),
    ("Mon", "2026-10-12", "07:00", "Instagram+Facebook", "Story", "w42-story-mon-1080x1920.png",
     "Pegasus is live. Link sticker → pegasusleads.com", "", "/", "mon_story"),
    ("Mon", "2026-10-12", "08:30", "LinkedIn", "Text + image (boost $40)", "w42-ad-morning-drop-1200x628.png",
     "Today I'm launching Pegasus.\n\nI kept watching good contractors and agents find out about work after it was gone. But almost every job leaves a trail first: a permit, a plat, a bid, a sale, an expired listing.\n\nPegasus reads that public record every morning, ranks it for your trade or your farm, and predicts what comes next: a new home means framing now, roofing in about six weeks, a deck within a year.\n\nIt's live in Hampton Roads today, and Source Scout maps any US county on request.\n\nThe first 100 customers keep 40% off for life. 14 days free, no card.",
     "#construction #realestate #proptech #contractors #leadgeneration", "/", "mon_linkedin"),
    ("Mon", "2026-10-12", "12:00", "X", "Post + image", "w42-ad-morning-drop-1200x628.png",
     "Every permit, bid, sale and storm in your area is on file before the job is posted.\n\nPegasus ranks it for your trade every morning at 7. Live today. 14 days free.",
     "", "/", "mon_x"),
    ("Mon", "2026-10-12", "18:00", "TikTok+YouTube Shorts", "Video", "Commercial 15 s · Contractors",
     "The job is already on file. You just can't see it yet. Pegasus: 14 days free.", "#contractor #construction #roofing #deckbuilder", "/", "mon_tiktok"),
    ("Mon", "2026-10-12", "09:00", "Google Business Profile", "Update + image", "w42-ad-founding-1080x1080.png",
     "Pegasus is live: construction and real estate leads from public records, ranked every morning. First 100 customers keep 40% off for life.",
     "", "/", "mon_gbp"),

    # ---------------------------------------------------------------- TUE 10/13 · Contractors: "Filed before it's posted"
    ("Tue", "2026-10-13", "07:30", "Instagram+Facebook+LinkedIn", "Carousel (5)", "w42-car-tue-1..5-1080x1350.png",
     "Every job in your town is filed before it's posted.\n\n1. The permit is filed days to months before anyone's hired.\n2. The project follows a sequence: one new home hires 14 trades in order.\n3. Whoever calls first sets the price everyone else is compared to.\n\nSee what was filed near you this week: free city lookup, no signup.",
     "#contractor #construction #building #remodeling #roofing #decks", "/leads", "tue_carousel"),
    ("Tue", "2026-10-13", "12:00", "TikTok+Instagram Reels", "UGC", "UGC Script 1 · 'My 7am' (creator) or founder version",
     "This is how I find jobs before they're posted.", "#contractor #deckbuilder #construction #smallbusiness", "/", "tue_ugc1"),
    ("Tue", "2026-10-13", "17:00", "X", "Post", "w42-car-tue-3-1080x1350.png",
     "A new-home permit is a schedule:\n\nFraming: weeks 1–6\nRoofing: weeks 5–10\nHVAC, plumbing, electric: weeks 6–12\nFlooring, paint: months 3–5\nDeck, fence, pool: months 4–12\n\nKnow your week before anyone calls.",
     "", "/", "tue_x"),
    ("Tue", "2026-10-13", "19:00", "Facebook Groups (value post)", "Text", "none",
     "Tip for anyone tired of buying shared leads: most decks, additions and new homes pull a permit with the city before a contractor is chosen. In most cities that's public. Check your city's permit portal once a week (or let a tool do it every morning) and call while the owner is still deciding.",
     "", "", "tue_groups"),

    # ---------------------------------------------------------------- WED 10/14 · Real estate: "5 public signs"
    ("Wed", "2026-10-14", "07:30", "Instagram+Facebook+LinkedIn", "Carousel (6)", "w42-car-wed-1..6-1080x1350.png",
     "5 public signs a home is about to hit the market, all from property records, none of it about the people:\n\n1. Long ownership + high equity\n2. An expired or withdrawn listing\n3. Absentee owner with an open code case\n4. Fix-up permits before a sale\n5. New tax or court filings\n\nPegasus stacks all five into one likely-to-sell score for every home in your farm, plus your MLS expireds at 7am.",
     "#realtor #realestateagent #listings #realestate #realestateinvesting", "/for/real-estate-agent", "wed_carousel"),
    ("Wed", "2026-10-14", "12:00", "TikTok+Instagram Reels", "UGC", "UGC Script 3 · 'Expired at midnight' (agent creator)",
     "Every expired listing in my farm, on my phone by 7am.", "#realtor #realestateagent #expiredlistings", "/for/real-estate-agent", "wed_ugc3"),
    ("Wed", "2026-10-14", "17:00", "X", "Post + image", "w42-ad-expired-1200x628.png",
     "Agents: an expired listing gets a wave of calls the morning it appears.\n\nConnect your MLS to Pegasus and expireds in your farm land as private leads by 7am, next to a likely-to-sell score for every home.",
     "", "/for/real-estate-agent", "wed_x"),
    ("Wed", "2026-10-14", "18:30", "LinkedIn", "Text", "none",
     "A question for agents: how do you decide who to call in your farm each week?\n\nWe score every home by how likely it is to sell in the next 12 months, using only property facts (years owned, equity, absentee ownership, recent permits and filings). Never anything about the people living there.\n\nCurious what your farm looks like? 14 days free at pegasusleads.com.",
     "#realestate #realtor #proptech", "/for/real-estate-agent", "wed_linkedin"),

    # ---------------------------------------------------------------- THU 10/15 · Prediction + storm
    ("Thu", "2026-10-15", "07:30", "Instagram+Facebook", "Story", "w42-story-thu-1080x1920.png",
     "One permit. 14 trades. Know your week. Link sticker → pegasusleads.com", "", "/", "thu_story"),
    ("Thu", "2026-10-15", "12:00", "Instagram Reels+TikTok+YouTube Shorts", "Screen + VO", "Founder quick hit · 'One permit, 14 trades'",
     "One new-home permit hires 14 trades in a predictable order. Pegasus tells each trade when its window opens.",
     "#construction #framing #hvac #roofing #plumbing #electrician", "/", "thu_reel"),
    ("Thu", "2026-10-15", "15:00", "Facebook+Instagram", "Image", "w42-ad-storm-1080x1350.png",
     "Roofers: when hail hits, the first truck on the street usually gets the conversation.\n\nPegasus maps NOAA hail and wind reports to your service area within hours and scores the roofs most likely to need you by morning.",
     "#roofing #roofer #stormdamage #hail #siding", "/for/roofer", "thu_storm"),
    ("Thu", "2026-10-15", "17:00", "X", "Post", "none",
     "Hail last night?\n\nBy 7am Pegasus has the swath on your service area and the roofs inside it scored: roof age, new owners, open permits.\n\nFirst truck on the street wins.",
     "", "/for/roofer", "thu_x"),

    # ---------------------------------------------------------------- FRI 10/16 · Cost of waiting + founding
    ("Fri", "2026-10-16", "07:30", "Instagram+Facebook+LinkedIn", "Carousel (4)", "w42-car-fri-1..4-1080x1350.png",
     "What one missed job actually costs you.\n\nExample: a $12,000 job at 25% margin is $3,000 of profit. Miss one a month and that's $36,000 a year.\n\nPegasus Growth is $107/month at founding price, locked for life. Run your own numbers with the calculator on our homepage.",
     "#contractor #smallbusiness #construction #businessgrowth", "/#calculator", "fri_carousel"),
    ("Fri", "2026-10-16", "12:00", "TikTok+Instagram Reels", "UGC", "UGC Script 5 · 'Shared leads vs public record'",
     "There's a free-to-find version of every job you're paying for.", "#contractor #leadgeneration #homeadvisor #construction", "/", "fri_ugc5"),
    ("Fri", "2026-10-16", "17:00", "X", "Post + image", "w42-ad-founding-1200x628.png",
     "First 100 Pegasus customers keep 40% off for life.\n\n14 days free, no card. When the seats are gone, they're gone.",
     "", "/app/signup?offer=founding", "fri_x"),

    # ---------------------------------------------------------------- SAT 10/17 · Founder story
    ("Sat", "2026-10-17", "09:00", "TikTok+Instagram Reels+YouTube Shorts+LinkedIn", "Founder video", "UGC Script 6 · founder story",
     "Why I built Pegasus. Every job in your town is on file before it's posted. Free 14 days, first 100 keep 40% off for life.",
     "#founder #construction #realestate #smallbusiness", "/", "sat_founder"),
    ("Sat", "2026-10-17", "10:00", "Instagram+Facebook", "Story", "w42-story-sat-1080x1920.png",
     "Founding seats are going. Tap to claim yours.", "", "/app/signup?offer=founding", "sat_story"),

    # ---------------------------------------------------------------- SUN 10/18 · Weekly data post (live)
    ("Sun", "2026-10-18", "16:00", "Instagram+Facebook+LinkedIn+X", "Carousel/Image from live data", "pegasus marketing weekly-posts → dist/weekly/<city>.md + banner",
     "This week in [city]: [N] new projects filed, worth about [$]. (Generated from live data on Sunday; paste the caption from dist/weekly/<city>.md.)",
     "#hamptonroads #virginiabeach #norfolk #chesapeake #construction", "/leads", "sun_weekly"),
    ("Sun", "2026-10-18", "18:00", "Instagram+Facebook", "Story", "Screenshot of /leads/va/<city> (your phone)",
     "What got filed near you this week → link sticker to the city page.", "", "/leads", "sun_story"),
]

X_LIMIT = 280


def x_text(caption: str, url: str) -> str:
    return f"{caption}\n\n{url}"


def main() -> None:
    rows = []
    for day, date, time, platform, fmt, asset, caption, tags, path, cid in sorted(POSTS, key=lambda p: (p[1], p[2])):
        source = platform.split("+")[0].split(" ")[0].lower()
        url = link(path, source, cid) if path else ""
        if platform == "X":
            # X counts every link as 23 characters
            assert len(caption) + 2 + 23 <= X_LIMIT, f"{cid}: X post too long ({len(caption)})"
        rows.append({"day": day, "date": date, "time_et": time, "platform": platform, "format": fmt, "asset": asset,
                     "caption": caption, "hashtags": tags, "link": url})
    with (HERE / "schedule.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    md = ["# Social posts · week of Oct 12–18, 2026", "",
          "Generated from `build_schedule.py`. Import `schedule.csv` into Postiz or Buffer, or post by hand. Times are Eastern.",
          "Images are in `marketing/dist/weeks/2026-10-12/` (run `pegasus marketing week`).", ""]
    current = None
    for r in rows:
        if r["day"] != current:
            current = r["day"]
            md += ["", f"## {r['day']} {r['date']}", ""]
        md += [f"### {r['time_et']} · {r['platform']} · {r['format']}", f"**Asset:** {r['asset']}", ""]
        md += [r["caption"].replace("\n", "  \n"), ""]
        if r["hashtags"]:
            md += [r["hashtags"], ""]
        if r["link"]:
            md += [f"Link: {r['link']}", ""]
    (HERE / "posts.md").write_text("\n".join(md).replace("\n\n\n", "\n\n") + "\n")
    print(f"{len(rows)} posts → schedule.csv, posts.md")


if __name__ == "__main__":
    main()
