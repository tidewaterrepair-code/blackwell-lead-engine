"""Cut the Pegasus brand pack into app and marketing assets.

Sources (supplied artwork, kept in the repo):
  marketing/brand/source/logo-primary.png  512x512 primary logo (app corner logo)
  marketing/brand/source/brand-pack.webp   1536x1024 sheet: splash logo, app icon, social profile/cover, website hero

Run after replacing either source (e.g. with higher-resolution originals; crop boxes scale automatically):
  pip install pillow && pegasus marketing brand
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

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
    rgb = im.convert("RGB")
    r, g, b = rgb.split()
    peak = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = peak.point(lambda v: 0 if v <= lo else 255 if v >= hi else round((v - lo) * 255 / (hi - lo)))
    px, apx = rgb.load(), alpha.load()
    out = Image.new("RGBA", rgb.size)
    opx = out.load()
    for y in range(rgb.size[1]):
        for x in range(rgb.size[0]):
            a = apx[x, y]
            if a == 0:
                opx[x, y] = (0, 0, 0, 0)
                continue
            cr, cg, cb = px[x, y]
            f = 255 / a
            opx[x, y] = (min(255, round(cr * f)), min(255, round(cg * f)), min(255, round(cb * f)), a)
    return out


def feather(im: Image.Image, frac: float = 0.07) -> Image.Image:
    """Fade alpha to zero toward every edge, so a cut-out never shows a hard rectangle."""
    w, h = im.size
    edge = Image.new("L", (w, h), 0)
    px = edge.load()
    fx, fy = max(1, w * frac), max(1, h * frac)
    for y in range(h):
        vy = min(1.0, y / fy, (h - 1 - y) / fy)
        for x in range(w):
            px[x, y] = round(255 * max(0.0, min(vy, x / fx, (w - 1 - x) / fx)))
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

    # --- primary logo (top corner of the app)
    logo = Image.open(SRC / "logo-primary.png")
    lb = {k: scale_box(v, logo.size, (LOGO_BASE, LOGO_BASE)) for k, v in LOGO_BOXES.items()}
    full = trim(key_black(logo.crop(scale_box((0, 0, 512, 462), logo.size, (LOGO_BASE, LOGO_BASE)))))
    save(full, STATIC / "logo.png")
    save(trim(key_black(logo.crop(lb["emblem"]))), STATIC / "logo-mark.png")
    save(trim(key_black(logo.crop(lb["wordmark"]))), STATIC / "logo-wordmark.png")
    # Email header (Gmail/Outlook need PNG): the wordmark on the email's black header
    save(trim(key_black(logo.crop(lb["wordmark"]))), STATIC / "email-wordmark.png")

    # --- brand pack sheet
    pack = Image.open(SRC / "brand-pack.webp").convert("RGB")
    pb = {k: scale_box(v, pack.size, PACK_BASE) for k, v in PACK_BOXES.items()}
    # Splash art keyed off its black background so it floats on the splash page with no visible edges
    save(feather(key_black(pack.crop(pb["splash"]), lo=16, hi=130), 0.05), STATIC / "splash.png")
    icon = square(pack.crop(pb["app-icon"]))
    for name, size in (("pegasus-512.png", 512), ("pegasus-192.png", 192), ("apple-touch-icon.png", 180)):
        save(upscale(icon, size), STATIC / name)
    # Favicon: the emblem alone reads better than the detailed tile at 32 px
    mark = trim(key_black(logo.crop(lb["emblem"])))
    fav = Image.new("RGBA", (64, 64), (11, 10, 8, 255))
    m = mark.copy()
    m.thumbnail((56, 56), Image.LANCZOS)
    fav.alpha_composite(m, ((64 - m.width) // 2, (64 - m.height) // 2))
    save(rounded(fav).resize((32, 32), Image.LANCZOS), STATIC / "pegasus-32.png")
    # Website: text-free hero art as WebP (fast LCP), and the splash art as WebP with alpha
    site = STATIC.parent / "site"
    site.mkdir(parents=True, exist_ok=True)
    city = pack.crop(pb["hero-city"])
    city = city.resize((round(city.width * 1.6), round(city.height * 1.6)), Image.LANCZOS)
    city = city.filter(ImageFilter.UnsharpMask(radius=1.4, percent=50, threshold=2))
    save(city, site / "hero-city.webp", quality=80, method=6)
    save(city.resize((480, round(480 * city.height / city.width)), Image.LANCZOS), site / "hero-city-480.webp",
         quality=55, method=6)  # phones show it faded; keep it tiny
    logo_art = Image.open(STATIC / "splash.png")
    save(logo_art, site / "hero-logo.webp", quality=88, method=6)
    small = logo_art.resize((360, round(360 * logo_art.height / logo_art.width)), Image.LANCZOS)
    save(small, site / "hero-logo-360.webp", quality=68, method=6)  # phones: faster LCP
    for name in ("social-profile", "social-cover", "website-hero"):
        save(pack.crop(pb[name]), PACK_OUT / f"{name}.png")
    save(rounded(upscale(icon, 512)), PACK_OUT / "app-icon-rounded.png")
    return written


if __name__ == "__main__":
    for p in main():
        print(p.relative_to(ROOT))
