"""Make 4x versions of the supplied brand artwork with Real-ESRGAN, so the splash and hero art stay sharp full-screen.

The supplied sheet is 1536x1024, which leaves the splash logo only 444 px wide. This writes
marketing/brand/source/brand-pack-4x.webp and logo-primary-4x.png; `pegasus marketing brand` prefers them.

One-off tool (not needed by the app). Needs PyTorch and the public Real-ESRGAN x4plus weights:
  python -m venv /tmp/up && /tmp/up/bin/pip install torch pillow numpy
  curl -LO https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
  /tmp/up/bin/python scripts/upscale_brand_sources.py RealESRGAN_x4plus.pth
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.nn import functional as F

SRC = Path(__file__).resolve().parents[1] / "marketing" / "brand" / "source"


class ResidualDenseBlock(nn.Module):
    def __init__(self, nf: int = 64, gc: int = 32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        return self.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf: int = 64, gc: int = 32):
        super().__init__()
        self.rdb1, self.rdb2, self.rdb3 = ResidualDenseBlock(nf, gc), ResidualDenseBlock(nf, gc), ResidualDenseBlock(nf, gc)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    """Real-ESRGAN x4plus generator (same layer names as the published weights)."""

    def __init__(self, nf: int = 64, blocks: int = 23, gc: int = 32):
        super().__init__()
        self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(blocks)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


@torch.no_grad()
def upscale(model: RRDBNet, im: Image.Image, tile: int = 192, pad: int = 12) -> Image.Image:
    """4x upscale in overlapping tiles (keeps memory flat on a CPU-only box)."""
    arr = torch.from_numpy(np.asarray(im.convert("RGB"), dtype=np.float32) / 255).permute(2, 0, 1)[None]
    _, _, h, w = arr.shape
    out = torch.zeros((1, 3, h * 4, w * 4))
    tiles = [(y, x) for y in range(0, h, tile) for x in range(0, w, tile)]
    for i, (y, x) in enumerate(tiles, 1):
        y0, x0, y1, x1 = max(0, y - pad), max(0, x - pad), min(h, y + tile + pad), min(w, x + tile + pad)
        res = model(arr[:, :, y0:y1, x0:x1])
        ty, tx = min(tile, h - y), min(tile, w - x)
        out[:, :, y * 4:(y + ty) * 4, x * 4:(x + tx) * 4] = \
            res[:, :, (y - y0) * 4:(y - y0 + ty) * 4, (x - x0) * 4:(x - x0 + tx) * 4]
        print(f"  tile {i}/{len(tiles)}", end="\r", flush=True)
    print()
    data = (out[0].clamp(0, 1).permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
    return Image.fromarray(data)


def main(weights: str) -> None:
    torch.set_num_threads(max(1, torch.get_num_threads()))
    model = RRDBNet()
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state.get("params_ema", state), strict=True)
    model.eval()
    jobs = [("logo-primary.png", "logo-primary-4x.png", {}),
            ("brand-pack.webp", "brand-pack-4x.webp", {"quality": 92, "method": 6})]
    for src, dst, kw in jobs:
        print(f"{src} -> {dst}")
        upscale(model, Image.open(SRC / src)).save(SRC / dst, **kw)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "RealESRGAN_x4plus.pth")
