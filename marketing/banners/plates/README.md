# Background plates

Photographic backgrounds for the banners. Drop a file named `<plate>.jpg` (or .png/.webp) in this folder and
`pegasus marketing render` uses it right away. Until then, a code-drawn night-city scene stands in.

**Rules for every plate**
- **No text, logos, letters, numbers, UI or watermarks.** Pegasus draws all text, pins and cards on top so they're always spelled right and editable.
- **Square, 2048 × 2048 or larger.** One square plate crops cleanly to feed (1:1), portrait (4:5), story (9:16) and link (1.91:1) sizes. Set `focus:` in `copy.yaml` to keep the subject in frame.
- **Black-and-gold grade.** Deep blacks, warm amber/gold light, cinematic contrast, slight haze. Matches the brand palette (#0B0A08, #E2B25A, #F08A2C).
- **Leave dark negative space** where the copy goes: the left half for most layouts, the top third for stories.
- **No real people's likeness, no real company logos, no recognizable real addresses.**

| Plate | Used by | Prompt |
|---|---|---|
| `pegasus-sky` | brand-hero, founding, og-image | Majestic dark bronze-and-gold winged horse (Pegasus) rearing in a stormy dusk sky above a modern American coastal city, wings fully spread, dramatic golden backlight breaking through clouds, faint glowing gold data lines and map grid over the city below, cinematic, epic scale, deep black shadows, warm amber highlights, ultra-detailed, photorealistic, no text |
| `aerial-dusk` | real-data, data-dollars, timeline | Aerial drone view at dusk of a growing suburban neighborhood with new homes under construction (framing, roofs going on), streets glowing with warm golden light, dark surroundings, subtle glowing gold grid lines connecting houses like a data map, cinematic black-and-gold color grade, photorealistic, no text, empty dark sky at top left |
| `contractor` | contractors, hero-trades | Rugged construction contractor seen from behind and slightly to the side, wearing a dark hard hat and tool belt, looking at a new house frame under construction at golden hour, sunset backlight with sparks of warm light, shallow depth of field, cinematic black-and-gold grade, subject on the right third, dark empty space on the left, photorealistic, no text, no logos |
| `agent` | agents | Professional real estate agent in a dark tailored blazer, seen from behind over her shoulder, holding a tablet showing a blurred map, standing in front of an upscale two-story home with warm lit windows at dusk, cinematic black-and-gold grade, subject on the right third, dark empty space on the left, photorealistic, no readable screen text, no logos |
| `truck-overlook` | everywhere, launch | Black pickup truck parked on a dark hilltop overlooking a glowing coastal city skyline and suburbs at night, warm golden city lights, faint glowing gold map pins of light scattered over neighborhoods, dramatic dusk sky, cinematic black-and-gold grade, wide composition, dark foreground, photorealistic, no text, no badges or logos |
| `storm-roofs` | storm | Dark storm clouds with lightning rolling over a suburban neighborhood at dusk, hail falling, wet rooftops catching warm golden streetlight, dramatic and moody, cinematic black-and-gold grade, dark sky at top left for text, photorealistic, no text |
| `farm-street` | farm, exclusive | Upscale tree-lined residential street at golden hour, rows of well-kept two-story homes with warm lit windows, long shadows, slight haze, cinematic black-and-gold grade, homes on the right half, darker open space on the left, photorealistic, no text, no for-sale signs |

Regenerate any plate freely: only the image changes; every size re-renders from it.
