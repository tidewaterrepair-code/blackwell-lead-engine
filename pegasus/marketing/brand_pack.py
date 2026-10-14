"""Cut the Pegasus brand pack into app and marketing assets.

Sources (supplied artwork, kept in the repo):
  marketing/brand/source/logo-primary.png  512x512 primary logo (app corner logo)
  marketing/brand/source/brand-pack.webp   1536x1024 sheet: splash logo, app icon, social profile/cover, website hero

If 4x versions exist (logo-primary-4x.png, brand-pack-4x.webp, made by scripts/upscale_brand_sources.py),
they are used instead, so the splash and hero art stay sharp full-screen on retina displays.

Run after replacing a source (crop boxes scale automatically to any resolution):
  pip install pillow && pegasus marketing brand
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "marketing" / "brand" / "source"
STATIC = ROOT / "pegasus" / "web" / "static" / "brand"
PACK_OUT = ROOT / "marketing" / "brand" / "pack"

# Crop boxes measured on the original sizes; scaled if a larger original is dropped in.
LOGO_BASE = 512
LOGO_BOXES = {"emblem": (78, 26, 422, 368), "wordmark": (34, 370, 478, 456)}
PACK_BASE = (1536, 1024)
PACK_BOXES = {
    "splash": (4, 0, 448, 336),           # "Original logo (#2)": winged horse, globe, wordmark
    "app-icon": (461, 50, 703, 288),       # rounded gold tile
    "social-profile": (720, 42, 972, 294),
    "social-cover": (992, 22, 1534, 342),
    "website-hero": (0, 392, 1536, 1024),  # the full website mockup (reference only: its text is baked in)
    "hero-city": (1000, 560, 1536, 890),   # text-free city scene from the website mockup (sheet coordinates), homepage hero art
}


def scale_box(box, src_size, base_size):
    sx, sy = src_size[0] / base_size[0], src_size[1] / base_size[1]
    return tuple(round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(box))


def key_black(im: Image.Image, lo: int = 14, hi: int = 150) -> Image.Image:
    """Turn the black background transparent. Alpha follows brightness (like a 'screen' blend), and colors
    are un-premultiplied so the gold keeps its brightness on any background."""
    r, g, b = im.convert("RGB").split()
    peak = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = peak.point(lambda v: 0 if v <= lo else 255 if v >= hi else round((v - lo) * 255 / (hi - lo)))
    half, solid = alpha.point(lambda v: v // 2), alpha.point(lambda v: 255 if v else 0)
    chans = [ImageChops.multiply(ImageMath.lambda_eval(lambda a: (a["c"] * 255 + a["h"]) / a["a"],
                                                       c=c, a=alpha, h=half).convert("L"), solid)
             for c in (r, g, b)]
    return Image.merge("RGBA", (*chans, alpha))


def feather(im: Image.Image, frac: float = 0.07) -> Image.Image:
    """Fade alpha to zero toward every edge, so a cut-out never shows a hard rectangle."""
    w, h = im.size

    def ramp(n: int) -> list[int]:
        f = max(1, n * frac)
        return [round(255 * max(0.0, min(1.0, i / f, (n - 1 - i) / f))) for i in range(n)]

    hx, hy = Image.new("L", (w, 1)), Image.new("L", (1, h))
    hx.putdata(ramp(w))
    hy.putdata(ramp(h))
    edge = ImageChops.darker(hx.resize((w, h), Image.NEAREST), hy.resize((w, h), Image.NEAREST))
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), edge))
    return out


def trim(im: Image.Image, pad: int = 6) -> Image.Image:
    box = im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        return im
    l, t, r, b = box
    return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))


def rounded(im: Image.Image, radius_frac: float = 0.22) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=round(im.width * radius_frac),
                                           fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def source(name: str, hires: str) -> Image.Image:
    return Image.open(SRC / hires if (SRC / hires).exists() else SRC / name)


def fit(im: Image.Image, max_w: int) -> Image.Image:
    """Downscale to at most max_w wide (never upscale)."""
    if im.width <= max_w:
        return im
    return im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)


def square(im: Image.Image) -> Image.Image:
    s = min(im.size)
    l, t = (im.width - s) // 2, (im.height - s) // 2
    return im.crop((l, t, l + s, t + s))


def upscale(im: Image.Image, size: int) -> Image.Image:
    out = im.resize((size, size), Image.LANCZOS)
    return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2)) if size > im.width else out


def main() -> list[Path]:
    STATIC.mkdir(parents=True, exist_ok=True)
    PACK_OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def save(img: Image.Image, path: Path, **kw):
        img.save(path, optimize=True, **kw)
        written.append(path)

    # --- primary logo (top corner of the app). Sizes are about 3x their usual on-screen size.
    logo = source("logo-primary.png", "logo-primary-4x.png")
    lb = {k: scale_box(v, logo.size, (LOGO_BASE, LOGO_BASE)) for k, v in LOGO_BOXES.items()}
    full = trim(key_black(fit(logo.crop(scale_box((0, 0, 512, 462), logo.size, (LOGO_BASE, LOGO_BASE))), 480)))
    save(full, STATIC / "logo.png")
    mark = trim(key_black(fit(logo.crop(lb["emblem"]), 320)))
    save(mark, STATIC / "logo-mark.png")
    save(trim(key_black(fit(logo.crop(lb["wordmark"]), 640))), STATIC / "logo-wordmark.png")
    # Email header (Gmail/Outlook need PNG): the wordmark on the email's black header, kept light
    save(trim(key_black(fit(logo.crop(lb["wordmark"]), 480))), STATIC / "email-wordmark.png")

    # --- brand pack sheet
    pack = source("brand-pack.webp", "brand-pack-4x.webp").convert("RGB")
    pb = {k: scale_box(v, pack.size, PACK_BASE) for k, v in PACK_BOXES.items()}
    # Splash art keyed off its black background so it floats on any page with no visible edges.
    # PNG for the ad renderer, WebP (with alpha) for the app splash and sign-in screens.
    splash = feather(key_black(fit(pack.crop(pb["splash"]), 1600), lo=16, hi=130), 0.05)
    save(splash, STATIC / "splash.png")
    save(splash, STATIC / "splash.webp", quality=62, alpha_quality=60, method=6)
    icon = square(pack.crop(pb["app-icon"]))
    for name, size in (("pegasus-512.png", 512), ("pegasus-192.png", 192), ("apple-touch-icon.png", 180)):
        save(upscale(icon, size), STATIC / name)
    # Favicon: the emblem alone reads better than the detailed tile at 32 px
    fav = Image.new("RGBA", (64, 64), (11, 10, 8, 255))
    m = mark.copy()
    m.thumbnail((56, 56), Image.LANCZOS)
    fav.alpha_composite(m, ((64 - m.width) // 2, (64 - m.height) // 2))
    save(rounded(fav).resize((32, 32), Image.LANCZOS), STATIC / "pegasus-32.png")
    # Website: text-free city art and the full-screen splash art, as responsive WebP sets
    site = STATIC.parent / "site"
    site.mkdir(parents=True, exist_ok=True)
    city = pack.crop(pb["hero-city"])
    city = city.resize((1920, round(1920 * city.height / city.width)), Image.LANCZOS)
    save(city, site / "hero-city.webp", quality=78, method=6)
    save(fit(city, 480), site / "hero-city-480.webp", quality=55, method=6)  # phones show it faded; keep it tiny
    for w in (1600, 1000, 640):  # q60 is visually identical to q85 on this art at half the bytes
        save(fit(splash, w), site / f"hero-logo-{w}.webp", quality=60, alpha_quality=60, method=6)
    for name in ("social-profile", "social-cover", "website-hero"):
        save(fit(pack.crop(pb[name]), 2400), PACK_OUT / f"{name}.png")
    save(rounded(upscale(icon, 512)), PACK_OUT / "app-icon-rounded.png")
    return written


if __name__ == "__main__":
    for p in main():
        print(p.relative_to(ROOT))
