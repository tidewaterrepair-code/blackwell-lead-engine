"""Pegasus brand kit: the gold winged-horse emblem and every lockup built from it.

One source of truth. `pegasus marketing brand` writes the SVGs used by the site, the app,
emails and ads, and renders the PNG icons (favicons, PWA, Apple touch icon).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"

# Palette (also mirrored in frontend/src/index.css and web/static/site.css)
NIGHT = "#0B0A08"        # page background, near-black with a warm cast
GOLD = "#E2B25A"         # primary brand gold
GOLD_LIGHT = "#FFE3A3"   # highlights
GOLD_DEEP = "#9A6420"    # gold that passes contrast on light backgrounds
EMBER = "#F08A2C"        # warm accent (glows, pins)
IVORY = "#F6EFE2"        # text on dark

# Emblem geometry, 448 x 480 viewbox: three wing tiers (back to front), then the head.
WING_OUTER = ("M236 300 C246 150 170 30 96 4 C118 74 118 74 67 71 L40 70 C92 140 92 140 40 141 L12 142 "
              "C84 206 84 206 36 211 L10 214 C100 264 100 264 57 276 L34 282 C140 312 140 312 109 326 "
              "L92 334 Q192 350 230 362 Z")
WING_MID = ("M240 296 C248 190 200 96 140 70 C156 132 156 132 120 133 L100 134 C144 192 144 192 105 197 "
            "L84 200 C146 248 146 248 114 257 L96 262 C168 296 168 296 150 305 L140 310 Q210 334 238 346 Z")
WING_INNER = ("M246 290 C252 226 224 168 186 150 C200 204 200 204 171 201 L156 200 C192 248 192 248 165 251 "
              "L150 252 C198 284 198 284 184 293 L176 298 Q222 320 246 330 Z")
HEAD = ("M150 476 C152 392 170 304 208 232 C232 186 258 152 286 128 L290 76 L312 120 C318 124 324 130 330 138 "
        "C356 170 382 212 404 254 C416 276 428 294 432 310 C434 322 426 330 414 330 C402 330 392 324 382 318 "
        "C360 314 340 302 324 286 C312 274 298 274 290 288 C280 306 272 340 266 380 C262 412 260 444 260 476 Z")
MANE = "M300 126 C276 150 254 186 238 228 C226 262 214 300 206 340"
CHEEK = "M330 250 C345 262 360 268 378 270"


def emblem_group(p: str = "pg", mono: str | None = None) -> str:
    """The emblem as SVG markup (defs + shapes). `p` prefixes gradient ids so several can share a page;
    `mono` draws it in one flat color (for tiny sizes, emails or single-color print)."""
    edge = 'stroke="#5C340B" stroke-width="2.5" stroke-opacity=".5" stroke-linejoin="round"'
    if mono:
        fills = [mono] * 4
        defs = ""
        edge = f'stroke="{NIGHT}" stroke-width="3" stroke-opacity=".35" stroke-linejoin="round"'
    else:
        fills = [f"url(#{p}w1)", f"url(#{p}w2)", f"url(#{p}w3)", f"url(#{p}h)"]
        stops = [("#6E4210", "#B27A2A", "#F6D48A"), ("#8A5518", "#D19A42", "#FFE6A6"),
                 ("#A86E24", "#E8B75E", "#FFF0C8")]
        defs = "".join(
            f'<linearGradient id="{p}w{i + 1}" x1="1" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{a}"/>'
            f'<stop offset=".55" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            for i, (a, b, c) in enumerate(stops))
        defs += (f'<linearGradient id="{p}h" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF2C9"/>'
                 '<stop offset=".4" stop-color="#F0C064"/><stop offset=".78" stop-color="#C38428"/>'
                 '<stop offset="1" stop-color="#7A4A14"/></linearGradient>')
        defs = f"<defs>{defs}</defs>"
    detail = "#7A4A14" if not mono else NIGHT
    return (f'{defs}<path d="{WING_OUTER}" fill="{fills[0]}" {edge}/><path d="{WING_MID}" fill="{fills[1]}" {edge}/>'
            f'<path d="{WING_INNER}" fill="{fills[2]}" {edge}/><path d="{HEAD}" fill="{fills[3]}" {edge}/>'
            f'<path d="{MANE}" fill="none" stroke="{detail}" stroke-width="5" stroke-linecap="round" opacity=".45"/>'
            f'<ellipse cx="344" cy="196" rx="9" ry="6" transform="rotate(40 344 196)" fill="#1A1206"/>'
            f'<ellipse cx="414" cy="302" rx="6" ry="4" transform="rotate(50 414 302)" fill="#1A1206" opacity=".8"/>'
            f'<path d="{CHEEK}" fill="none" stroke="{detail}" stroke-width="3" opacity=".4" stroke-linecap="round"/>')


def emblem_svg(p: str = "pg", mono: str | None = None, size: int | None = None) -> str:
    dims = f' width="{size}" height="{round(size * 480 / 448)}"' if size else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 480"{dims} role="img" '
            f'aria-label="Pegasus">{emblem_group(p, mono)}</svg>')


def app_icon_svg(p: str = "ic") -> str:
    """Rounded black tile with a warm glow behind the emblem."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>'
            f'<radialGradient id="{p}glow" cx=".42" cy=".38" r=".7"><stop offset="0" stop-color="#3A2610"/>'
            f'<stop offset=".55" stop-color="#16110A"/><stop offset="1" stop-color="{NIGHT}"/></radialGradient>'
            f'<linearGradient id="{p}rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFE3A3"/>'
            f'<stop offset=".5" stop-color="#9A6420"/><stop offset="1" stop-color="#FFE3A3"/></linearGradient></defs>'
            f'<rect x="8" y="8" width="496" height="496" rx="112" fill="url(#{p}glow)" stroke="url(#{p}rim)" '
            f'stroke-width="6"/><g transform="translate(70 62) scale(.84)">{emblem_group(p)}</g></svg>')


@lru_cache(maxsize=4)
def _font_b64(name: str) -> str:
    path = STATIC / "fonts" / name
    return base64.b64encode(path.read_bytes()).decode() if path.exists() else ""


def wordmark_svg(theme: str = "dark", p: str = "wm", tagline: bool = True) -> str:
    """Horizontal lockup: emblem + PEGASUS (Cinzel) + DATA & LEAD TECHNOLOGY.
    Fonts are embedded so the SVG renders identically as an <img>, in email clients that support SVG,
    and in design tools."""
    sub = "#C9B48C" if theme == "dark" else GOLD_DEEP
    cinzel, inter = _font_b64("cinzel-latin-600.woff2"), _font_b64("inter-latin.woff2")
    style = ""
    if cinzel:
        style += f'@font-face{{font-family:PgCinzel;src:url(data:font/woff2;base64,{cinzel}) format("woff2");}}'
    if inter:
        style += f'@font-face{{font-family:PgInter;src:url(data:font/woff2;base64,{inter}) format("woff2");font-weight:100 900;}}'
    word_fill = f"url(#{p}gold)" if theme == "dark" else "#17120A"
    h = 200 if tagline else 168
    tag = (f'<text x="214" y="178" font-family="PgInter, Inter, sans-serif" font-weight="600" font-size="22" '
           f'letter-spacing="9" fill="{sub}">DATA &amp; LEAD TECHNOLOGY</text>' if tagline else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {h}" role="img" aria-label="Pegasus, data and '
            f'lead technology"><defs><style>{style}</style><linearGradient id="{p}gold" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#FFF1C9"/><stop offset=".5" stop-color="{GOLD}"/>'
            f'<stop offset="1" stop-color="#A86E24"/></linearGradient></defs>'
            f'<g transform="translate(8 8) scale(.36)">{emblem_group(p)}</g>'
            f'<text x="208" y="128" font-family="PgCinzel, Cinzel, serif" font-weight="600" font-size="104" '
            f'letter-spacing="6" fill="{word_fill}">PEGASUS</text>{tag}</svg>')


def write_svgs(marketing_brand: Path | None = None) -> list[Path]:
    brand = STATIC / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    out = {
        brand / "pegasus-mark.svg": emblem_svg(),
        brand / "pegasus-icon.svg": app_icon_svg(),
        brand / "pegasus-wordmark-dark.svg": wordmark_svg("dark"),
        brand / "pegasus-wordmark-light.svg": wordmark_svg("light", p="wl"),
    }
    if marketing_brand:
        marketing_brand.mkdir(parents=True, exist_ok=True)
        out.update({marketing_brand / "logo-mark.svg": emblem_svg(),
                    marketing_brand / "logo-mark-mono-gold.svg": emblem_svg(mono=GOLD),
                    marketing_brand / "logo-mark-mono-black.svg": emblem_svg(mono="#111111"),
                    marketing_brand / "logo-app-icon.svg": app_icon_svg(),
                    marketing_brand / "logo-horizontal-dark.svg": wordmark_svg("dark"),
                    marketing_brand / "logo-horizontal-light.svg": wordmark_svg("light", p="wl")})
    for path, svg in out.items():
        path.write_text(svg)
    return list(out)


def render_pngs() -> list[Path]:
    """Favicons and app icons from the SVGs (needs Playwright + Chromium; see banners.py)."""
    import os

    from playwright.sync_api import sync_playwright

    brand = STATIC / "brand"
    icon = app_icon_svg()
    targets = {"pegasus-512.png": 512, "pegasus-192.png": 192, "apple-touch-icon.png": 180, "pegasus-32.png": 32}
    written = []
    exe = os.environ.get("CHROMIUM_PATH")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        for name, size in targets.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            svg = icon if size > 32 else app_icon_svg().replace('stroke-width="6"', 'stroke-width="0"')
            page.set_content(f'<html><body style="margin:0;background:transparent">'
                             f'<div style="width:{size}px;height:{size}px">{svg.replace("<svg ", f"<svg width={size} height={size} ")}'
                             f"</div></body></html>")
            path = brand / name
            page.screenshot(path=str(path), omit_background=True)
            page.close()
            written.append(path)
        # Email header wordmark: PNG because Gmail and Outlook don't render SVG. Drawn at 2x for retina.
        page = browser.new_page(viewport={"width": 640, "height": 168})
        page.set_content(f'<html><body style="margin:0;background:transparent">'
                         f'{wordmark_svg("dark", p="em").replace("<svg ", "<svg width=640 height=168 ")}</body></html>')
        page.wait_for_timeout(200)
        path = brand / "email-wordmark.png"
        page.screenshot(path=str(path), omit_background=True)
        written.append(path)
        browser.close()
    return written
