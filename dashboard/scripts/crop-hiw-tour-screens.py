#!/usr/bin/env python3
"""Extract in-phone UI from Karen tour mockups. See landingDesignAssets.howItWorksScreens."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'public' / 'brand' / 'landing' / 'app-screens'
TOUR_DIR = ROOT / 'tour'
OUT_DIR = ROOT / 'screens'

# left, top, right, bottom
CROPS: dict[str, tuple[int, int, int, int]] = {
    '04-ai-setup.png': (412, 114, 690, 902),
    '05-smart-answers.png': (36, 114, 676, 902),
    '06-smart-follow-up.png': (36, 114, 676, 902),
    '07-integrations.png': (36, 114, 676, 902),
    '09-requests.png': (36, 114, 676, 902),
    '10-users.png': (412, 114, 690, 902),
    '11-subscription.png': (36, 114, 676, 902),
    '12-ai-limits.png': (412, 114, 690, 902),
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for file, box in CROPS.items():
        src = TOUR_DIR / file
        num, slug = file.replace('.png', '').split('-', 1)
        dest = OUT_DIR / f'{num}-{slug}-screen.png'
        crop = Image.open(src).crop(box)
        crop.save(dest)
        print(f'{file} -> {dest.name} {crop.size}')


if __name__ == '__main__':
    main()
