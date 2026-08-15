"""Checksum + perceptual hash for product image matching (0 AI credits)."""

from __future__ import annotations

import hashlib
import io
from typing import Any

from PIL import Image


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def compute_average_phash(content: bytes) -> str:
    try:
        with Image.open(io.BytesIO(content)) as img:
            gray = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(gray.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return f"{int(bits, 2):016x}"
    except Exception:
        return hashlib.sha256(content[: min(len(content), 4096)]).hexdigest()[:16]


def phash_hamming_similarity(left_hex: str, right_hex: str) -> float:
    try:
        left = int(left_hex, 16)
        right = int(right_hex, 16)
    except ValueError:
        return 0.0
    distance = (left ^ right).bit_count()
    return max(0.0, 1.0 - distance / 64.0)


def compute_fingerprint(content: bytes) -> dict[str, str]:
    return {"sha256": sha256_hex(content), "phash": compute_average_phash(content)}


def compute_color_histogram(content: bytes, bins: int = 16) -> list[float]:
    try:
        with Image.open(io.BytesIO(content)) as img:
            rgb = img.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
            pixels = list(rgb.getdata())
    except Exception:
        digest = hashlib.sha256(content).digest()
        return [float(b) / 255.0 for b in digest[: bins * 3]]
    hist = [0.0] * (bins * 3)
    step = 256 / bins
    for r, g, b in pixels:
        hist[int(r / step)] += 1
        hist[bins + int(g / step)] += 1
        hist[2 * bins + int(b / step)] += 1
    total = float(len(pixels)) or 1.0
    return [v / total for v in hist]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = sum(a * a for a in left) ** 0.5
    norm_r = sum(b * b for b in right) ** 0.5
    if norm_l == 0 or norm_r == 0:
        return 0.0
    return float(dot / (norm_l * norm_r))


# Shape/structure (pHash) dominates; color histogram is secondary.
PHASH_WEIGHT = 0.85
HISTOGRAM_WEIGHT = 0.15


def combined_image_similarity(
    *,
    query_fp: dict[str, str],
    query_hist: list[float],
    entry: dict[str, Any],
) -> float:
    if query_fp.get("sha256") and entry.get("sha256") == query_fp["sha256"]:
        return 1.0
    phash_sim = phash_hamming_similarity(
        str(query_fp.get("phash") or ""),
        str(entry.get("phash") or entry.get("phash_stub") or ""),
    )
    hist = entry.get("histogram")
    hist_sim = cosine_similarity(query_hist, list(hist or [])) if isinstance(hist, list) else 0.0
    # Weighted blend — same model different color should still match via pHash.
    blended = (phash_sim * PHASH_WEIGHT) + (hist_sim * HISTOGRAM_WEIGHT)
    # Exact checksum already returned; strong pHash alone can clear threshold.
    if phash_sim >= 0.92:
        return max(blended, phash_sim)
    return blended
