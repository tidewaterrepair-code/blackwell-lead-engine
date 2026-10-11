"""Ad banner renderer: copy.yaml -> self-contained HTML -> PNG in every size (headless Chromium)."""

from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path

import yaml

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
MARK = (STATIC / "brand" / "pegasus-mark.svg").read_text() if (STATIC / "brand" / "pegasus-mark.svg").exists() else ""


@lru_cache(maxsize=1)
def _font_css() -> str:
    out = []
    for family, name in (("Inter", "inter-latin.woff2"), ("Space Grotesk", "space-grotesk-latin.woff2")):
        path = STATIC / "fonts" / name
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode()
            out.append(f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{b64}) format("woff2");'
                       f"font-weight:100 900;}}")
    return "".join(out)


def parse_size(size: str) -> tuple[int, int]:
    w, h = size.lower().split("x")
    return int(w), int(h)


def layout(w: int, h: int) -> str:
    if h <= 120:
        return "strip"  # leaderboards
    if w <= 200:
        return "tower"  # skyscrapers
    if w < 400:
        return "small"  # 300x250
    if w / h >= 1.6:
        return "wide"
    return "tall" if h / w >= 1.6 else "square"


def banner_html(b: dict, size: str) -> str:
    w, h = parse_size(size)
    mode = layout(w, h)
    unit = min(w, h) / 100  # 1 unit = 1% of the short side
    gold = b.get("accent") == "gold"
    e = {k: html.escape(str(b.get(k, ""))) for k in ("kicker", "headline", "sub", "cta")}
    stat = b.get("stat") or {}
    mark = MARK.replace("<svg ", f'<svg width="{unit * 9:.0f}" height="{unit * 9:.0f}" ')
    head_size = {"strip": h * 0.30, "tower": w * 0.15, "small": w * 0.085, "wide": h * 0.112,
                 "square": w * 0.075, "tall": w * 0.098}[mode]
    sub_size = head_size * 0.42
    show_sub = mode not in ("strip", "tower", "small")
    show_stat = bool(stat) and mode in ("square", "tall", "wide")
    flex = "row" if mode in ("strip", "wide") else "column"
    pad = {"strip": "0 18px", "tower": "18px 12px", "small": "16px"}.get(mode, f"{unit * 7:.0f}px")
    ring = "#FFC24B" if gold else "#7C5CFF"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_font_css()}
*{{box-sizing:border-box;margin:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:Inter,sans-serif;color:#F4F6FF;
  background:radial-gradient({w * 0.9:.0f}px {h * 0.9:.0f}px at 0% 0%,rgba(124,92,255,.45),transparent 60%),
  radial-gradient({w * 0.7:.0f}px {h * 0.7:.0f}px at 100% 100%,rgba(34,211,238,.28),transparent 60%),#070A1E}}
.wrap{{position:relative;width:100%;height:100%;padding:{pad};display:flex;flex-direction:{flex};
  justify-content:{'center' if mode in ('tall', 'tower') else 'space-between'};align-items:{'center' if flex == 'row' else 'flex-start'};gap:{unit * 4:.0f}px}}
.rings{{position:absolute;right:-{w * 0.12:.0f}px;top:-{h * 0.12:.0f}px;width:{max(w, h) * 0.65:.0f}px;height:{max(w, h) * 0.65:.0f}px;
  border-radius:50%;border:2px solid rgba(124,92,255,.25);box-shadow:0 0 0 {unit * 8:.0f}px rgba(124,92,255,.06),0 0 0 {unit * 16:.0f}px rgba(34,211,238,.04)}}
.brand{{display:flex;align-items:center;gap:{unit * 2:.0f}px;font:700 {max(12, unit * 4.2):.0f}px "Space Grotesk";}}
.kicker{{font-weight:700;letter-spacing:.16em;text-transform:uppercase;font-size:{max(9, sub_size * 0.62):.0f}px;color:{'#FFC24B' if gold else '#22D3EE'};margin-bottom:{unit * 1.5:.0f}px}}
h1{{font:700 {head_size:.0f}px/1.04 "Space Grotesk";letter-spacing:-.03em;max-width:{w * (0.62 if flex == 'row' else 0.92):.0f}px}}
h1 em{{font-style:normal;background:linear-gradient(135deg,#7C5CFF,#22D3EE);-webkit-background-clip:text;color:transparent}}
p{{font-size:{sub_size:.0f}px;line-height:1.35;color:#A9B0D6;margin-top:{unit * 2.5:.0f}px;max-width:{w * 0.8:.0f}px}}
.cta{{display:inline-block;font-weight:700;font-size:{max(11, sub_size * 0.95):.0f}px;color:#fff;padding:{max(6, unit * 2.4):.0f}px {max(12, unit * 4.5):.0f}px;
  border-radius:{max(8, unit * 2.6):.0f}px;background:{'linear-gradient(135deg,#FFD36E,#FFAE2B);color:#1b1300' if gold else 'linear-gradient(135deg,#7C5CFF,#22D3EE)'};
  box-shadow:0 10px 30px -10px rgba(124,92,255,.8);white-space:nowrap}}
.stat{{position:absolute;right:{unit * 7:.0f}px;bottom:{unit * 7:.0f}px;width:{unit * 30:.0f}px;height:{unit * 30:.0f}px;border-radius:50%;
  border:{unit * 1.6:.0f}px solid {ring};display:grid;place-items:center;text-align:center;background:rgba(15,21,54,.7)}}
.stat b{{display:block;font:700 {unit * 8:.0f}px "Space Grotesk"}} .stat span{{font-size:{unit * 2.6:.0f}px;color:#A9B0D6;text-transform:uppercase;letter-spacing:.1em}}
</style></head><body><div class="wrap"><div class="rings"></div>
<div style="position:relative">{'' if mode == 'strip' else f'<div class="brand">{mark}Pegasus</div><div style="height:{unit * 6:.0f}px"></div>'}
<div class="kicker">{e['kicker']}</div><h1>{_emphasize(e['headline'])}</h1>{f'<p>{e["sub"]}</p>' if show_sub else ''}
{'' if flex == 'row' else f'<div style="height:{unit * 5:.0f}px"></div><span class="cta">{e["cta"]}</span>'}</div>
{f'<span class="cta" style="position:relative">{e["cta"]}</span>' if flex == 'row' else ''}
{f'<div class="stat"><div><b>{html.escape(str(stat.get("value", "")))}</b><span>{html.escape(str(stat.get("label", "")))}</span></div></div>' if show_stat and flex != 'row' else ''}
</div></body></html>"""


def _emphasize(headline: str) -> str:
    """Gradient on the last sentence fragment for visual punch."""
    parts = headline.rsplit(". ", 1)
    if len(parts) == 2 and parts[1]:
        return f"{parts[0]}. <em>{parts[1]}</em>"
    words = headline.split(" ")
    if len(words) > 3:
        return " ".join(words[:-2]) + " <em>" + " ".join(words[-2:]) + "</em>"
    return headline


def load_copy(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def render_all(copy_path: Path, out_dir: Path, only: list[str] | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright

    data = load_copy(copy_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    import os

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
                page.wait_for_timeout(150)
                path = out_dir / f"{b['id']}-{size}.png"
                page.screenshot(path=str(path))
                page.close()
                written.append(path)
        browser.close()
    return written
