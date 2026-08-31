#!/usr/bin/env python3
"""Extract in-phone UI from Karen tour mockups → 780×1688 screens.

See landingDesignAssets.howItWorksScreens. Real app handoffs (owner-copilot,
navigation, integrations, live-chat, settings) stay primary; this script only
rebuilds tour-derived screens.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "public" / "brand" / "landing" / "app-screens"
TOUR_DIR = ROOT / "tour"
OUT_DIR = ROOT / "screens"

# Phone interior only (no mint canvas, no device bezel) on 880×1021 tour comps.
BOX = (360, 108, 730, 922)
TARGET = (780, 1688)

TOUR_SLUGS = (
    "01-owner-copilot",
    "02-side-menu",
    "03-dashboard",
    "04-ai-setup",
    "05-smart-answers",
    "06-smart-follow-up",
    "07-integrations",
    "08-live-chat",
    "09-requests",
    "10-users",
    "11-subscription",
    "12-ai-limits",
    "13-settings",
)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for slug in TOUR_SLUGS:
        src = TOUR_DIR / f"{slug}.png"
        dest = OUT_DIR / f"{slug}-screen.png"
        crop = Image.open(src).convert("RGB").crop(BOX)
        crop.resize(TARGET, Image.Resampling.LANCZOS).save(dest, optimize=True)
        print(f"{src.name} -> {dest.name} {TARGET[0]}x{TARGET[1]}")


if __name__ == "__main__":
    main()
