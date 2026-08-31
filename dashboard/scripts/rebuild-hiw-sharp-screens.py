#!/usr/bin/env python3
"""Rebuild How-it-works phone screens at sharp 780×1688.

Sources (priority):
- Real app handoffs under app-screens/*.png
- High-res mobile mockups under mobile/linas-ai/docs/
- Content Management handoff for AI Setup (newest admin list UI)

Do not upscale soft Karen tour comps — those look blurry in the phone frame.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parents[1] / "public" / "brand" / "landing" / "app-screens"
OUT = ROOT / "screens"
TARGET = (780, 1688)

SOURCES: dict[str, Path] = {
    "01-owner-copilot-screen.png": ROOT / "owner-copilot.png",
    "02-side-menu-screen.png": ROOT / "navigation.png",
    "03-dashboard-screen.png": REPO
    / "mobile/linas-ai/docs/mockups/linas-dashboard-active-populated-approx.png",
    "04-ai-setup-screen.png": ROOT / "content-management.png",
    "07-integrations-screen.png": ROOT / "integrations.png",
    "08-live-chat-screen.png": ROOT / "live-chat.png",
    "11-subscription-screen.png": REPO
    / "mobile/linas-ai/docs/subscription-mockups/sub-mock-current-lite.png",
    "13-settings-screen.png": ROOT / "settings.png",
}


def fit_cover(im: Image.Image, target: tuple[int, int] = TARGET) -> Image.Image:
    im = im.convert("RGB")
    tw, th = target
    target_aspect = tw / th
    w, h = im.size
    src_aspect = w / h
    if src_aspect > target_aspect:
        nh = h
        nw = int(round(h * target_aspect))
        left = (w - nw) // 2
        crop = im.crop((left, 0, left + nw, h))
    else:
        nw = w
        nh = int(round(w / target_aspect))
        top = max(0, (h - nh) // 2)
        crop = im.crop((0, top, w, top + nh))
    return crop.resize(target, Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for dest_name, src in SOURCES.items():
        if not src.is_file():
            raise SystemExit(f"missing source: {src}")
        out = fit_cover(Image.open(src))
        dest = OUT / dest_name
        out.save(dest, optimize=True)
        print(f"{src.name} -> {dest.name} {TARGET[0]}x{TARGET[1]}")


if __name__ == "__main__":
    main()
