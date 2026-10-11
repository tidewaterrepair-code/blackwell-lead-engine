"""Cinematic ad banners: copy.yaml -> self-contained HTML -> PNG in every size (headless Chromium).

Each banner is a full-bleed background *plate* (an AI photo in marketing/banners/plates/, or a
code-drawn night-city scene when the photo doesn't exist yet) with crisp, editable layers on top:
headline, gold map pins, lead cards, a phone mockup, feature rows, logo and call to action.
Text is never baked into the photo, so copy stays spelled right and editable in every size.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import random
import re
from functools import lru_cache
from pathlib import Path

import yaml


STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
PLATES = Path.cwd() / "marketing" / "banners" / "plates"

ICONS = {  # 24px line icons (lucide-style)
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    "chart": '<path d="M4 20V14M10 20V9M16 20V4M2 20h20"/>',
    "home": '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/>',
    "hammer": '<path d="m15 12-8.5 8.5a2.1 2.1 0 0 1-3-3L12 9"/><path d="M17.6 15 22 10.6M20 12.6 11.4 4a4.2 4.2 0 0 0-5.9 0l8.5 8.5"/>',
    "roof": '<path d="M2 12 12 4l10 8"/><path d="M5 10v9h14v-9"/><path d="M9 14h6"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0 5 5L22 13.6l-8.4 8.4a2.8 2.8 0 0 1-4-4L18 9.6l-2.3-2.3z" transform="scale(.9) translate(1 1)"/><path d="m3 21 6-6"/>',
    "tools": '<path d="M14 7 7 14M4 17l3 3M17 4l3 3-6 6-3-3z"/><path d="m3 3 4 4"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="M12 8v5M12 16h.01"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.5"/>',
    "dollar": '<path d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "cloud": '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9a4.5 4.5 0 0 0 1 9z"/><path d="M9 21l1-2M13 21l1-2"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "sparkles": '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "map": '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
}


def icon(name: str, cls: str = "ic") -> str:
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, ICONS["bolt"])}</svg>')


@lru_cache(maxsize=1)
def _font_css() -> str:
    out = []
    for family, name, weight in (("Inter", "inter-latin.woff2", "100 900"), ("Oswald", "oswald-latin.woff2", "200 700"),
                                 ("Cinzel", "cinzel-latin-600.woff2", "600")):
        path = STATIC / "fonts" / name
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode()
            out.append(f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{b64}) format("woff2");'
                       f"font-weight:{weight};}}")
    return "".join(out)


def parse_size(size: str) -> tuple[int, int]:
    w, h = size.lower().split("x")
    return int(w), int(h)


def layout(w: int, h: int) -> str:
    if h <= 120:
        return "strip"   # leaderboards
    if w <= 200:
        return "tower"   # skyscrapers
    if w < 400:
        return "small"   # 300x250
    if w / h >= 1.6:
        return "wide"    # link ads, og image
    return "tall" if h / w >= 1.6 else "square"


# ---------------------------------------------------------------- plates

def plate_path(name: str | None) -> Path | None:
    if not name:
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = PLATES / f"{name}{ext}"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=16)
def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def brand_img(name: str, cls: str = "") -> str:
    """Brand artwork from the image pack (pegasus/web/static/brand, cut by `pegasus marketing brand`)."""
    path = STATIC / "brand" / name
    src = _data_uri(path) if path.exists() else ""
    return f'<img class="{cls}" src="{src}" alt="Pegasus">'


def lockup() -> str:
    """Horizontal logo for ad footers: the emblem beside the wordmark."""
    return f'<span class="lockup">{brand_img("logo-mark.png", "lk-mark")}{brand_img("logo-wordmark.png", "lk-word")}</span>'


def fallback_scene(w: int, h: int, seed: str, scene: str = "city") -> str:
    """Code-drawn cinematic night city: warm horizon, skyline with lit windows, glowing street grid."""
    rnd = random.Random(seed)
    horizon = h * (0.5 if scene == "city" else 0.62)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice">',
             '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#07060A"/>'
             '<stop offset=".55" stop-color="#1C1209"/><stop offset=".85" stop-color="#5A3510"/>'
             '<stop offset="1" stop-color="#8A5518"/></linearGradient>'
             '<radialGradient id="sun" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#FFB547" stop-opacity=".55"/>'
             '<stop offset="1" stop-color="#FFB547" stop-opacity="0"/></radialGradient>'
             '<linearGradient id="ground" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#140D06"/>'
             '<stop offset="1" stop-color="#050404"/></linearGradient>'
             '<filter id="blur"><feGaussianBlur stdDeviation="2"/></filter></defs>',
             f'<rect width="{w}" height="{horizon:.0f}" fill="url(#sky)"/>',
             f'<ellipse cx="{w * rnd.uniform(.55, .8):.0f}" cy="{horizon:.0f}" rx="{w * .55:.0f}" ry="{h * .22:.0f}" fill="url(#sun)"/>']
    # clouds
    for _ in range(7):
        cx, cy = rnd.uniform(0, w), rnd.uniform(0, horizon * .7)
        parts.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{w * rnd.uniform(.15, .35):.0f}" ry="{h * rnd.uniform(.02, .05):.0f}" '
                     f'fill="#3A2412" opacity="{rnd.uniform(.25, .5):.2f}" filter="url(#blur)"/>')
    # skyline
    x = 0.0
    sky_h = h * .16
    while x < w:
        bw = rnd.uniform(w * .02, w * .06)
        bh = rnd.uniform(sky_h * .25, sky_h) * (1.6 if rnd.random() < .12 else 1)
        top = horizon - bh
        parts.append(f'<rect x="{x:.0f}" y="{top:.0f}" width="{bw:.0f}" height="{bh + 2:.0f}" fill="#0C0907"/>')
        for wy in range(int(top + 4), int(horizon - 3), max(4, int(h / 180))):
            for wx in range(int(x + 3), int(x + bw - 3), max(4, int(w / 260))):
                if rnd.random() < .22:
                    parts.append(f'<rect x="{wx}" y="{wy}" width="{max(1, w // 600)}" height="{max(1, h // 700)}" '
                                 f'fill="#FFC867" opacity="{rnd.uniform(.35, .9):.2f}"/>')
        x += bw + rnd.uniform(0, w * .01)
    # ground: perspective street grid with warm lights
    parts.append(f'<rect y="{horizon:.0f}" width="{w}" height="{h - horizon:.0f}" fill="url(#ground)"/>')
    vx = w * .5
    for i in range(-14, 15):
        x2 = vx + i * w * .16
        parts.append(f'<line x1="{vx + i * w * .012:.0f}" y1="{horizon:.0f}" x2="{x2:.0f}" y2="{h}" '
                     f'stroke="#E08A2A" stroke-opacity=".22" stroke-width="{max(1, w / 900):.1f}"/>')
    y, step = horizon, h * .008
    while y < h:
        parts.append(f'<line x1="0" y1="{y:.0f}" x2="{w}" y2="{y:.0f}" stroke="#E08A2A" stroke-opacity=".16" '
                     f'stroke-width="{max(1, w / 1000):.1f}"/>')
        step *= 1.32
        y += step
    for _ in range(int(w * h / 2400)):
        px, py = rnd.uniform(0, w), rnd.uniform(horizon, h)
        depth = (py - horizon) / (h - horizon)
        parts.append(f'<circle cx="{px:.0f}" cy="{py:.0f}" r="{max(.6, depth * w / 500):.1f}" fill="#FFC867" '
                     f'opacity="{rnd.uniform(.2, .8) * (.4 + depth * .6):.2f}"/>')
    parts.append("</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode("".join(parts).encode()).decode()


# ---------------------------------------------------------------- components

def headline_html(lines: list[str]) -> str:
    """Lines of the headline; *text* renders in gold."""
    out = []
    for line in lines:
        esc = html.escape(line)
        esc = re.sub(r"\*(.+?)\*", r'<span class="gold">\1</span>', esc)
        out.append(f"<span class='hl'>{esc}</span>")
    return "".join(out)


def _plain(lines: list[str]) -> str:
    return " ".join(l.replace("*", "") for l in lines)


def pin_html(p: dict, show_label: bool) -> str:
    label = ""
    if show_label and p.get("title"):
        label = (f'<div class="pin-card"><b>{html.escape(p["title"])}</b>'
                 f'{"<span>" + html.escape(p.get("sub", "")) + "</span>" if p.get("sub") else ""}'
                 f'{"<i>" + html.escape(p.get("meta", "")) + "</i>" if p.get("meta") else ""}</div>')
    side = "left" if p.get("label_side") == "left" else "right"
    return (f'<div class="pin {side}" style="left:{p["x"]}%;top:{p["y"]}%">'
            f'<svg class="drop" viewBox="0 0 24 32"><defs><linearGradient id="pg{p["x"]}{p["y"]}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#FFE7B0"/><stop offset="1" stop-color="#D08A2C"/></linearGradient></defs>'
            f'<path d="M12 31S2 19.5 2 11.5a10 10 0 0 1 20 0C22 19.5 12 31 12 31z" fill="url(#pg{p["x"]}{p["y"]})" '
            f'stroke="#5C340B" stroke-width="1"/><circle cx="12" cy="11.5" r="3.8" fill="#1A1206"/></svg>{label}</div>')


HOUSE_THUMB = ('<svg viewBox="0 0 64 48"><defs><linearGradient id="ht" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#3A2A16"/><stop offset="1" stop-color="#120D07"/></linearGradient></defs>'
               '<rect width="64" height="48" fill="url(#ht)"/><path d="M10 26 32 10l22 16" stroke="#E2B25A" stroke-width="2.4" '
               'fill="none"/><path d="M15 23v17h34V23" stroke="#E2B25A" stroke-width="2.4" fill="#1F160C"/>'
               '<rect x="21" y="28" width="7" height="6" fill="#FFC867"/><rect x="36" y="28" width="7" height="6" fill="#FFC867"/>'
               '<rect x="29" y="31" width="6" height="9" fill="#5A3A14"/></svg>')


def card_html(c: dict) -> str:
    value = f'<em>{html.escape(c["value"])}</em>' if c.get("value") else ""
    return (f'<div class="lead"><div class="thumb">{HOUSE_THUMB}</div><div class="lead-t"><b>{html.escape(c["title"])}</b>'
            f'<span>{html.escape(c.get("sub", ""))}</span>{value}'
            f'{"<i>" + html.escape(c["meta"]) + "</i>" if c.get("meta") else ""}</div></div>')


def phone_html(b: dict, w: int, h: int) -> str:
    rows = "".join(card_html(c) for c in b.get("cards", [])[:4])
    pins = "".join(pin_html(p, False) for p in b.get("phone_pins", [
        {"x": 22, "y": 30}, {"x": 58, "y": 22}, {"x": 40, "y": 55}, {"x": 74, "y": 48}, {"x": 30, "y": 78}]))
    return (f'<div class="phone"><div class="screen"><div class="status"><span>9:41</span><span>●●●</span></div>'
            f'<div class="map" style="background-image:url({fallback_scene(400, 300, "phone-map", "map")})">{pins}</div>'
            f'<div class="rows">{rows}</div></div></div>')


def features_html(items: list) -> str:
    return '<div class="features">' + "".join(
        f'<div class="feat">{icon(i)}<span>{html.escape(t)}</span></div>' for i, t in items) + "</div>"


def bullets_html(items: list) -> str:
    return '<ul class="bullets">' + "".join(
        f'<li>{icon(i)}<span>{html.escape(t)}</span></li>' for i, t in items) + "</ul>"


def timeline_html(steps: list) -> str:
    return '<div class="timeline">' + "".join(
        f'<div class="step"><span class="lbl">{html.escape(t)}</span><span class="bar" style="margin-left:{s}%;width:{wd}%">'
        f'</span><span class="when">{html.escape(wh)}</span></div>' for t, s, wd, wh in steps) + "</div>"


def stat_html(stat: dict) -> str:
    return (f'<div class="stat"><div><b>{html.escape(str(stat.get("value", "")))}</b>'
            f'<span>{html.escape(str(stat.get("label", "")))}</span></div></div>')


# ---------------------------------------------------------------- page

def banner_html(b: dict, size: str) -> str:
    w, h = parse_size(size)
    mode = layout(w, h)
    t = b.get("layout", "audience")
    u = min(w, h) / 100 if mode not in ("wide",) else h / 100
    lines = b["headline"] if isinstance(b["headline"], list) else [b["headline"]]
    if mode in ("small", "tower", "strip") and b.get("short"):
        lines = b["short"]
    longest = max(len(l.replace("*", "")) for l in lines)
    # Headline size: the mode's base size, shrunk until the longest line fits the text column.
    col = text_width(mode, t)
    if t == "hero" and mode in ("square", "tall", "wide"):
        col = .9
    base = {"square": 9.6, "tall": 8.6, "wide": 11.5, "small": 12.5, "tower": 15.5, "strip": 30}[mode] * u
    if mode == "strip":
        base = h * .3
    hsize = min(base, (w * col) / (max(longest, 6) * .5))
    if mode == "strip":
        hsize = min(hsize, (w * col) / (len(_plain(lines)) * .5))
    cta_text = (b.get("cta_short") if mode in ("small", "tower", "strip") else None) or b.get("cta", "")
    cta_px = {"tower": min(w * .085, w * .78 / (max(len(cta_text), 1) * .56)),
              "small": min(w * .045, w * .5 / (max(len(cta_text), 1) * .56)),
              "strip": min(h * .2, w * .24 / (max(len(cta_text), 1) * .56))}.get(mode)
    plate = plate_path(b.get("plate"))
    bg = _data_uri(plate) if plate else fallback_scene(w, h, b["id"] + size, b.get("scene", "city"))
    focus = b.get("focus", "50% 50%")
    tall_visual = mode in ("square", "tall", "wide")

    labels = mode in ("square", "tall") or (mode == "wide" and t != "hero")
    pins = "".join(pin_html(p, show_label=labels)
                   for p in (b.get("pins") or [])[: (4 if tall_visual else 2 if mode == "tower" else 0)])
    visual = ""
    if tall_visual:
        if t == "phone":
            visual = phone_html(b, w, h)
        elif t == "cards":
            visual = '<div class="cards">' + "".join(card_html(c) for c in b.get("cards", [])[:3]) + "</div>"
        elif t == "timeline" and b.get("timeline"):
            visual = timeline_html(b["timeline"])
        elif b.get("stat"):
            visual = stat_html(b["stat"])
    ribbon = f'<div class="ribbon">{html.escape(b["ribbon"])}</div>' if b.get("ribbon") and mode != "strip" else ""
    kicker = (f'<div class="kicker">{html.escape(b["kicker"])}</div>'
              if b.get("kicker") and not b.get("ribbon") and mode in ("square", "tall", "wide", "small") else "")
    sub = (f'<p class="sub">{html.escape(b["sub"])}</p>' if b.get("sub") and mode in ("square", "tall", "wide") else "")
    bullets = bullets_html(b["bullets"]) if b.get("bullets") and mode in ("square", "tall") else ""
    features = features_html(b["features"]) if b.get("features") and mode in ("square", "tall") else ""
    footer = (f'<div class="footer">{html.escape(b["footer"])}</div>' if b.get("footer")
              and mode in ("square", "tall", "wide") and not features else "")
    cta_style = f' style="font-size:{cta_px:.1f}px"' if cta_px else ""
    cta = (f'<span class="cta"{cta_style}>{html.escape(cta_text)}{icon("arrow", "arr") if mode not in ("strip", "tower") else ""}</span>'
           if cta_text else "")
    if mode == "strip":
        logo = f'<div class="mark" style="width:{h * .7:.0f}px">{brand_img("logo-mark.png")}</div>'
    elif mode in ("tower", "small"):
        logo = f'<div class="logo">{brand_img("logo-wordmark.png")}</div>'
    elif t == "hero":
        logo = f'<div class="logo">{brand_img("splash.png")}</div>'
    else:
        logo = f'<div class="logo">{lockup()}</div>'
    side = b.get("side_words") if t == "hero" and mode in ("square", "wide") else None
    side_html = ('<div class="side">' + "".join(f"<span>{html.escape(s)}</span>" for s in side) + "</div>") if side else ""
    tagline = (f'<div class="tagline">{headline_html(b["tagline"])}</div>'
               if t == "hero" and b.get("tagline") and mode in ("square", "tall", "wide") else "")

    if t == "hero" and mode in ("square", "tall", "wide"):
        body = (f'<div class="hero-lock">{logo}{tagline}{cta if mode == "wide" else ""}</div>{features}{footer}')
    elif mode == "strip":
        body = f'{logo}<h1>{headline_html([" ".join(lines)])}</h1>{cta}'
    else:
        body = (f'<div class="text">{ribbon}{kicker}<h1>{headline_html(lines)}</h1>{sub}{bullets}</div>'
                f'{visual}<div class="bottom">{logo}{cta}</div>{features}{footer}')

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--u:{u:.3f}px;--gold:linear-gradient(180deg,#FFF1C9 0%,#E9BC66 45%,#B47A2C 100%);--ivory:#F6EFE2}}
body{{width:{w}px;height:{h}px;overflow:hidden;position:relative;font-family:Inter,sans-serif;color:var(--ivory);background:#0B0A08}}
.bg{{position:absolute;inset:0;background:url({bg}) {focus}/cover no-repeat}}
.shade{{position:absolute;inset:0;background:{_shade(mode, t)}}}
.vign{{position:absolute;inset:0;box-shadow:inset 0 0 calc(var(--u)*18) rgba(0,0,0,.75)}}
.frame{{position:absolute;inset:calc(var(--u)*1.2);border:1px solid rgba(226,178,90,.28);pointer-events:none}}
h1{{font:700 {hsize:.1f}px/1.0 Oswald,sans-serif;text-transform:uppercase;letter-spacing:.005em;text-shadow:0 2px 12px rgba(0,0,0,.6)}}
.hl{{display:block;white-space:nowrap}}
.gold{{background:var(--gold);-webkit-background-clip:text;background-clip:text;color:transparent;text-shadow:none;filter:drop-shadow(0 2px 6px rgba(0,0,0,.5))}}
.kicker{{font:600 calc(var(--u)*2.1)/1 Inter;letter-spacing:.24em;text-transform:uppercase;color:#E9BC66;margin-bottom:calc(var(--u)*2)}}
.ribbon{{display:inline-block;font:700 calc(var(--u)*3.2)/1 Oswald;letter-spacing:.08em;text-transform:uppercase;color:#1A1206;
  background:var(--gold);padding:calc(var(--u)*1) calc(var(--u)*2.2);margin-bottom:calc(var(--u)*2.4);
  clip-path:polygon(0 0,100% 0,97% 50%,100% 100%,0 100%);box-shadow:0 6px 18px rgba(0,0,0,.5)}}
.sub{{font:600 calc(var(--u)*2.5)/1.35 Inter;letter-spacing:.03em;text-transform:uppercase;color:#E8DCC6;margin-top:calc(var(--u)*2.4);max-width:calc(var(--u)*60);text-shadow:0 1px 8px rgba(0,0,0,.8)}}
.cta{{display:inline-flex;align-items:center;gap:calc(var(--u)*1.4);font:700 calc(var(--u)*3)/1 Oswald;letter-spacing:.06em;text-transform:uppercase;
  color:#1A1206;background:var(--gold);padding:calc(var(--u)*1.8) calc(var(--u)*3.4);border-radius:calc(var(--u)*1);
  box-shadow:0 0 0 1px #FFE7B0 inset,0 10px 30px -8px rgba(240,138,44,.65);white-space:nowrap}}
.arr{{width:1.1em;height:1.1em}}
.logo img,.mark img{{display:block;width:100%;height:auto}} .lockup{{display:flex;align-items:center;gap:4%}} .lockup .lk-mark{{width:24%;flex:none}} .lockup .lk-word{{width:72%}}
.ic{{width:calc(var(--u)*4.2);height:calc(var(--u)*4.2);color:#E9BC66;flex:none}}
.bullets{{list-style:none;margin-top:calc(var(--u)*3);display:grid;gap:calc(var(--u)*1.6)}}
.bullets li{{display:flex;align-items:center;gap:calc(var(--u)*1.8);font:600 calc(var(--u)*2.3)/1.2 Inter;text-transform:uppercase;letter-spacing:.06em;text-shadow:0 1px 6px rgba(0,0,0,.8)}}
.bullets .ic{{width:calc(var(--u)*3.6);height:calc(var(--u)*3.6)}}
.features{{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:space-around;padding:calc(var(--u)*3) calc(var(--u)*3) calc(var(--u)*3.6);
  background:linear-gradient(0deg,rgba(8,6,4,.95),rgba(8,6,4,.6) 70%,transparent)}}
.feat{{flex:1;display:flex;flex-direction:column;align-items:center;gap:calc(var(--u)*1.2);text-align:center;font:600 calc(var(--u)*1.9)/1.2 Inter;
  letter-spacing:.08em;text-transform:uppercase;border-left:1px solid rgba(226,178,90,.3);padding:0 calc(var(--u)*1)}}
.feat:first-child{{border-left:0}}
.footer{{position:absolute;left:0;right:0;bottom:calc(var(--u)*3.4);text-align:center;font:600 calc(var(--u)*2)/1 Inter;letter-spacing:.32em;text-transform:uppercase;color:#E8DCC6}}
.pin{{position:absolute;width:calc(var(--u)*4.4);transform:translate(-50%,-100%);filter:drop-shadow(0 0 calc(var(--u)*2) rgba(255,190,90,.8))}}
.pin .drop{{display:block;width:100%}}
.pin-card{{position:absolute;top:0;left:120%;min-width:calc(var(--u)*20);background:rgba(10,8,6,.82);border:1px solid rgba(226,178,90,.55);
  border-radius:calc(var(--u)*.8);padding:calc(var(--u)*1) calc(var(--u)*1.4);font:500 calc(var(--u)*1.6)/1.3 Inter;filter:none;box-shadow:0 8px 24px rgba(0,0,0,.6)}}
.pin.left .pin-card{{left:auto;right:120%}}
.pin-card b{{display:block;font:700 calc(var(--u)*1.9)/1.2 Oswald;letter-spacing:.06em;text-transform:uppercase;color:#FFE7B0}}
.pin-card span{{display:block;color:#E8DCC6}} .pin-card i{{display:block;font-style:normal;color:#A8977A;font-size:.9em}}
.lead{{display:flex;gap:calc(var(--u)*1.4);align-items:center;background:rgba(14,11,8,.86);border:1px solid rgba(226,178,90,.5);
  border-radius:calc(var(--u)*1);padding:calc(var(--u)*1);box-shadow:0 10px 30px rgba(0,0,0,.55)}}
.thumb{{width:calc(var(--u)*11);flex:none;border-radius:calc(var(--u)*.6);overflow:hidden;border:1px solid rgba(226,178,90,.35)}}
.thumb svg{{display:block;width:100%}}
.lead-t{{font:500 calc(var(--u)*1.7)/1.3 Inter;display:flex;flex-direction:column}}
.lead-t b{{font:700 calc(var(--u)*2)/1.15 Oswald;letter-spacing:.05em;text-transform:uppercase;color:#FFE7B0}}
.lead-t em{{font:700 calc(var(--u)*3)/1.1 Oswald;font-style:normal;color:#fff}} .lead-t i{{font-style:normal;color:#A8977A}}
.cards{{position:absolute;display:grid;gap:calc(var(--u)*2.2)}}
.phone{{position:absolute;border-radius:calc(var(--u)*5);padding:calc(var(--u)*1.1);background:linear-gradient(145deg,#3A2A16,#0C0A08 40%,#2A1E10);
  box-shadow:0 0 0 1px rgba(226,178,90,.6),0 30px 80px rgba(0,0,0,.8),0 0 calc(var(--u)*10) rgba(240,138,44,.25);transform:rotate(-6deg)}}
.screen{{width:100%;height:100%;border-radius:calc(var(--u)*4);overflow:hidden;background:#0B0A08;display:flex;flex-direction:column}}
.status{{display:flex;justify-content:space-between;padding:calc(var(--u)*1.4) calc(var(--u)*3);font:600 calc(var(--u)*1.5)/1 Inter;color:#E8DCC6}}
.map{{position:relative;flex:1.1;background-size:cover;border-bottom:1px solid rgba(226,178,90,.35)}}
.map .pin{{width:calc(var(--u)*3)}}
.rows{{flex:1.4;display:grid;gap:calc(var(--u)*1);padding:calc(var(--u)*1.2);align-content:start}}
.rows .lead{{padding:calc(var(--u)*.7)}} .rows .thumb{{width:calc(var(--u)*8)}}
.rows .lead-t{{font-size:calc(var(--u)*1.35)}} .rows .lead-t b{{font-size:calc(var(--u)*1.6)}}
.timeline{{position:absolute;display:grid;gap:calc(var(--u)*1.3);background:rgba(10,8,6,.78);border:1px solid rgba(226,178,90,.4);
  border-radius:calc(var(--u)*1.4);padding:calc(var(--u)*2.4)}}
.step{{display:grid;grid-template-columns:32% 1fr auto;align-items:center;gap:calc(var(--u)*1.4);font:600 calc(var(--u)*1.8)/1.2 Inter}}
.step .bar{{display:block;height:calc(var(--u)*1.4);border-radius:99px;background:var(--gold);box-shadow:0 0 calc(var(--u)*1.6) rgba(240,138,44,.6)}}
.step .when{{color:#A8977A;font-size:.9em;white-space:nowrap}}
.stat{{position:absolute;width:calc(var(--u)*26);height:calc(var(--u)*26);border-radius:50%;display:grid;place-items:center;text-align:center;
  background:radial-gradient(circle,rgba(30,20,8,.9),rgba(10,8,6,.85));border:calc(var(--u)*1.1) solid #E2B25A;box-shadow:0 0 calc(var(--u)*6) rgba(240,138,44,.5)}}
.stat b{{display:block;font:700 calc(var(--u)*8)/1 Oswald;background:var(--gold);-webkit-background-clip:text;background-clip:text;color:transparent}}
.stat span{{font:600 calc(var(--u)*1.9)/1 Inter;letter-spacing:.2em;text-transform:uppercase;color:#E8DCC6}}
.side{{position:absolute;right:calc(var(--u)*4);top:calc(var(--u)*6);display:grid;gap:calc(var(--u)*1.6);text-align:right;
  font:500 calc(var(--u)*1.9)/1 Inter;letter-spacing:.32em;text-transform:uppercase;color:#E8DCC6}}
.hero-lock{{position:absolute;left:50%;transform:translateX(-50%);text-align:center;display:flex;flex-direction:column;align-items:center}}
.tagline{{font:500 calc(var(--u)*3)/1.25 Oswald;letter-spacing:.14em;text-transform:uppercase;margin-top:calc(var(--u)*2.4)}}
.tagline .hl{{display:block;white-space:nowrap}}
{_mode_css(mode, t, w, h)}
</style></head><body><div class="bg"></div><div class="shade"></div><div class="vign"></div>{pins}{side_html}
<div class="wrap">{body}</div><div class="frame"></div></body></html>"""


def text_width(mode: str, t: str) -> float:
    """Fraction of the canvas width the text column may use (headline sizing and CSS agree)."""
    if mode in ("square",):
        return .5 if t in ("phone", "cards") else .6
    return {"tall": .86, "wide": .5 if t in ("phone", "cards", "timeline") else .56, "small": .86, "tower": .8,
            "strip": .58}[mode]


def _shade(mode: str, t: str) -> str:
    if t == "hero":
        return ("linear-gradient(180deg,rgba(8,6,4,.55) 0%,rgba(8,6,4,0) 30%,rgba(8,6,4,.15) 55%,rgba(8,6,4,.9) 100%)")
    if mode == "tall":
        return "linear-gradient(180deg,rgba(8,6,4,.88) 0%,rgba(8,6,4,.35) 40%,rgba(8,6,4,.25) 60%,rgba(8,6,4,.92) 100%)"
    if mode in ("strip", "small", "tower"):
        return "linear-gradient(90deg,rgba(8,6,4,.88),rgba(8,6,4,.55))"
    return "linear-gradient(90deg,rgba(8,6,4,.92) 0%,rgba(8,6,4,.65) 42%,rgba(8,6,4,.1) 75%),linear-gradient(0deg,rgba(8,6,4,.7),transparent 35%)"


def _mode_css(mode: str, t: str, w: int, h: int) -> str:
    """Placement of the text column, visual, logo and CTA for each canvas shape."""
    u = "var(--u)"
    if mode == "strip":
        return (f".wrap{{position:absolute;inset:0;display:flex;align-items:center;gap:{h * .16:.0f}px;padding:0 {h * .3:.0f}px}}"
                f".mark{{flex:none}} h1{{flex:1;white-space:nowrap}} .cta{{padding:{h * .14:.0f}px {h * .24:.0f}px}}"
                ".frame{inset:3px}")
    if mode == "tower":
        return (f".wrap{{position:absolute;inset:0;padding:{w * .1:.0f}px;display:flex;flex-direction:column}}"
                f".text{{margin-top:{h * .05:.0f}px}} .bottom{{margin-top:auto;display:flex;flex-direction:column;gap:{w * .1:.0f}px}}"
                f".ribbon{{font-size:{w * .07:.0f}px;padding:{w * .03:.0f}px {w * .05:.0f}px}} .logo{{width:100%}} .cta{{"
                f"padding:{w * .07:.0f}px {w * .04:.0f}px;justify-content:center}} .pin{{width:{w * .1:.0f}px}} .frame{{inset:4px}}")
    if mode == "small":
        return (f".wrap{{position:absolute;inset:0;padding:{w * .07:.0f}px;display:flex;flex-direction:column}}"
                f".ribbon{{font-size:{w * .04:.0f}px;padding:{w * .015:.0f}px {w * .03:.0f}px;margin-bottom:{w * .03:.0f}px}}"
                f".kicker{{font-size:{w * .03:.0f}px;margin-bottom:{w * .03:.0f}px}}"
                f".bottom{{margin-top:auto;display:flex;align-items:center;justify-content:space-between;gap:10px}} .logo{{width:38%;flex:none}}"
                f".cta{{padding:{w * .03:.0f}px {w * .035:.0f}px}} .frame{{inset:4px}}")
    if t == "hero":
        portrait = h > w * 1.1
        top = {"square": 24 if portrait else 22, "tall": 33, "wide": 14}[mode]
        lw = {"square": 60 if portrait else 52, "tall": 82, "wide": 36}[mode]
        extra = f".hero-lock .cta{{margin-top:calc({u}*3)}}" if mode == "wide" else ""
        return (f".hero-lock{{top:{top}%;width:{lw}%}} .hero-lock .logo{{width:100%}} .features .ic{{width:calc({u}*4.6);height:calc({u}*4.6)}}"
                f"{extra}")
    if mode == "wide":
        vis = {"phone": f".phone{{right:5%;top:8%;width:{h * .5:.0f}px;height:{h * .95:.0f}px}}",
               "cards": f".cards{{right:4%;top:12%;width:40%}}",
               "timeline": f".timeline{{right:4%;top:14%;width:42%}}"}.get(t, f".stat{{right:5%;top:50%;transform:translateY(-50%)}}")
        return (f".wrap{{position:absolute;inset:0}} .text{{position:absolute;left:5%;top:11%;width:{text_width(mode, t) * 100:.0f}%}}"
                f".bottom{{position:absolute;left:5%;bottom:9%;display:flex;align-items:center;gap:calc({u}*4)}}"
                f".logo{{width:calc({u}*44)}} .sub{{font-size:calc({u}*2.6);max-width:none}} {vis}"
                ".footer{display:none}")
    if mode == "tall":
        vis = {"phone": f".phone{{left:50%;top:39%;width:52%;height:40%;transform:translateX(-50%) rotate(-4deg)}}",
               "cards": f".cards{{left:7%;right:7%;top:44%}}",
               "timeline": f".timeline{{left:7%;right:7%;top:46%}}"}.get(t, f".stat{{right:8%;top:52%}}")
        return (f".wrap{{position:absolute;inset:0}} .text{{position:absolute;left:7%;right:7%;top:6%}}"
                f".bottom{{position:absolute;left:7%;right:7%;bottom:{'15%' if t != 'phone' else '13%'};display:flex;align-items:center;justify-content:space-between;gap:calc({u}*3)}}"
                f".logo{{width:calc({u}*52)}} {vis} .bullets{{grid-template-columns:1fr 1fr}}")
    # square / portrait
    portrait = h > w * 1.1
    vis = {"phone": f".phone{{right:4%;top:{'10' if not portrait else '14'}%;width:38%;height:{'66' if not portrait else '58'}%}}",
           "cards": f".cards{{right:4%;top:{'30' if not portrait else '33'}%;width:44%}}",
           "timeline": f".timeline{{left:6%;right:6%;top:{'44' if not portrait else '46'}%}}"}.get(
        t, f".stat{{right:6%;bottom:{'24' if not portrait else '22'}%}}")
    text_w = f"{text_width(mode, t) * 100:.0f}%"
    bottom = {"phone": "17", "cards": "9"}.get(t, "7")
    return (f".wrap{{position:absolute;inset:0}} .text{{position:absolute;left:6%;top:6%;width:{text_w}}}"
            f".bottom{{position:absolute;left:6%;right:6%;bottom:{bottom}%;display:flex;align-items:center;justify-content:space-between;gap:calc({u}*3)}}"
            f".logo{{width:calc({u}*42)}} {vis} .bullets{{grid-template-columns:{'1fr 1fr' if not portrait else '1fr'}}}")


def load_copy(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def render_all(copy_path: Path, out_dir: Path, only: list[str] | None = None) -> list[Path]:
    import os

    from playwright.sync_api import sync_playwright

    data = load_copy(copy_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    exe = os.environ.get("CHROMIUM_PATH")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for b in data["banners"]:
            if only and b["id"] not in only:
                continue
            for size in b.get("sizes", data["sizes"]):
                w, h = parse_size(size)
                page = browser.new_page(viewport={"width": w, "height": h})
                page.set_content(banner_html(b, size))
                page.wait_for_timeout(250)
                path = out_dir / f"{b['id']}-{size}.png"
                page.screenshot(path=str(path))
                page.close()
                written.append(path)
        browser.close()
    return written
