# Pegasus brand guide

## Name & tagline
- **Name:** Pegasus. **Descriptor:** data & lead technology.
- **Primary tagline:** *See the job before your competition does.*
- **Trades sub-brand:** Pegasus Trades: "Tomorrow's jobs are already on file."
- **Real estate sub-brand:** Pegasus Realty: "Know who's selling before they list."
- **Short hooks:** "Leads with lift." · "Get there first." · "Your unfair head start."

## Logo
The brand artwork is the supplied image pack. Sources live in `marketing/brand/source/`:

| Source | What it is |
|---|---|
| `logo-primary.png` | **Primary logo**: gold Pegasus in a ring above PEGASUS / DATA & LEAD TECHNOLOGY. The logo in the app's top corner. |
| `brand-pack.webp` | **Brand pack sheet**: the ornate rearing Pegasus with globe (splash screens), app icon, social profile, social cover and website hero. |

`pegasus marketing brand` (needs Pillow) cuts them into ready-to-use files: the black backgrounds are keyed out so the gold sits on any surface.

| File (`pegasus/web/static/brand/`) | Use |
|---|---|
| `logo.png` | Primary logo, transparent: sidebar top corner, login page corner |
| `logo-mark.png` | Emblem only: phone header, empty states, small spaces |
| `logo-wordmark.png` | PEGASUS + descriptor: ad footers, email header (`email-wordmark.png`) |
| `splash.png` | Ornate Pegasus from the pack: app splash screen, login art, hero ads |
| `pegasus-512/192.png`, `apple-touch-icon.png` | App icon from the pack (home screen, PWA) |
| `pegasus-32.png` | Favicon (the emblem on black) |

Pack pieces for later (`marketing/brand/pack/`): `social-profile.png`, `social-cover.png`, `website-hero.png` (the website splash design), `app-icon-rounded.png`.

**Higher resolution:** the sheet's pieces are small (the splash art is about 440 px wide, the app icon about 240 px). When you have the full-size originals, replace the files in `source/` and run `pegasus marketing brand` again; crop positions scale automatically.

Rules: don't recolor the gold, stretch the logo, or place it on a busy light photo. Keep clear space equal to the height of the horse's head around it.

## Color
| Role | Hex | Use |
|---|---|---|
| Night (base) | `#0B0A08` | Backgrounds, ad canvases, dark UI |
| Surface | `#16130F` | Cards on dark |
| Gold | `#E2B25A` | Primary brand: buttons, highlights, the mark |
| Gold light | `#FFE3A3` | Gradient highlights, glows |
| Gold deep | `#9A6420` | Gold on light backgrounds (passes contrast on ivory) |
| Ember | `#F08A2C` | Warm glows, map pins, "hot" |
| Ivory | `#F6EFE2` | Text on dark |
| Ivory page | `#FBF7EF` | Light-mode background |
| Green | `#2ECC8C` | Won deals, success |
| Red | `#F06060` | Errors, "do not call" |

**Signature gradient ("gold"):** `linear-gradient(180deg, #FFE3A3 0%, #E2B25A 55%, #B9802F 100%)`, used on buttons and the gold half of headlines.
Data-viz categories use the color-blind-validated family palette in `frontend/src/lib/tags.ts`, always paired with an icon and label.

## Type
- **Brand:** Cinzel 600, uppercase, letter-spaced. Only for the wordmark and rare ceremonial moments.
- **Display:** Oswald (600–700), uppercase in ads, sentence case in the app. One line in ivory, the payoff line in gold.
- **UI & body:** Inter (400/500/600). Small labels: uppercase, letter-spaced 0.08–0.3em.
- All three are open source (OFL), self-hosted and free to use in ads and video.

## Voice
- **Plainspoken, confident, a little cocky. Never hype.** Talk like a sharp foreman or a top agent, not a startup.
- Lead with the outcome ("first call", "jobs before they're posted"), then the proof (data source, timing).
- Use numbers from real data only. No fake testimonials, no fake counts.
- Real estate copy never references a person's hardship in the opening line and never targets protected characteristics.
- **Words we use:** jobs, leads, first call, Morning Drop, radar, predicted, your area, swipe.
- **Words we avoid:** synergy, revolutionary, AI-powered (as a headline), guaranteed, "motivated seller" in outreach copy.

## Imagery
- Real job sites, trucks at dawn, phones in hands with the app, map radar visuals, satellite/aerial neighborhood shots with glowing pins.
- **Look:** cinematic black and gold. Deep shadows, warm amber backlight, slight haze, glowing gold map pins and data lines.
- **Layering:** photo plate (no text in it) + dark scrim where copy sits + Oswald headline (ivory, payoff line gold) + gold CTA button + logo lockup. See `banners/copy.yaml` and `banners/plates/README.md`.
- AI-generated imagery must never depict real, identifiable people or real customers. Mark it as illustrative where required by platform rules.

## Social handles
`@pegasusleads` on Instagram, TikTok, YouTube, X, Facebook and LinkedIn. Profile image: `logo-app-icon.svg` exported at 1024×1024 (or `pegasus/web/static/brand/pegasus-512.png`).
