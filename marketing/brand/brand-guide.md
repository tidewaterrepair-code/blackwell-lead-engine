# Pegasus brand guide

## Name & tagline
- **Name:** Pegasus. **Descriptor:** data & lead technology.
- **Primary tagline:** *See the job before your competition does.*
- **Trades sub-brand:** Pegasus Trades: "Tomorrow's jobs are already on file."
- **Real estate sub-brand:** Pegasus Realty: "Know who's selling before they list."
- **Short hooks:** "Leads with lift." · "Get there first." · "Your unfair head start."

## Logo
- **Mark:** a gold heraldic Pegasus: horse head in profile with a three-tier wing rising behind it. Files: `logo-mark.svg` (gold), `logo-mark-mono-gold.svg` and `logo-mark-mono-black.svg` (single-color print, embroidery, stamps), `logo-app-icon.svg` (black tile with a gold rim).
- **Wordmark lockups:** `logo-horizontal-dark.svg` (gold on black) and `logo-horizontal-light.svg` (black on ivory). "PEGASUS" is set in Cinzel; the descriptor "DATA & LEAD TECHNOLOGY" in Inter, letter-spaced.
- Every logo file is generated from `pegasus/marketing/brand.py` (`pegasus marketing brand`), so the site, app, emails, icons and ads always match. Don't edit the SVGs by hand.
- Clear space: the height of the horse's ear on every side. Minimum size: 20 px for the mark, 140 px wide for the lockup.
- Don't recolor the gold, stretch the mark, or set the gold logo on a light busy photo. On photos, use a dark scrim behind it.

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
