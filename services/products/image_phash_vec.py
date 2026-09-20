"""64-d bit vector derived from product pHash — compact ANN, not Voyage multimodal."""

from __future__ import annotations

PHASH_DIM = 64


def phash_to_vec(phash: str) -> list[float]:
    raw = str(phash or "").strip().lower()
    if not raw:
        return []
    try:
        bits = f"{int(raw, 16):0{PHASH_DIM}b}"
    except ValueError:
        return []
    if len(bits) < PHASH_DIM:
        bits = bits.zfill(PHASH_DIM)
    return [1.0 if ch == "1" else 0.0 for ch in bits[:PHASH_DIM]]


def vec_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


def l2_sq(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 1e9
    return float(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
