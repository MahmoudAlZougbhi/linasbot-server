"""
Process-wide guard: identical WhatsApp text to the same recipient within a short window.

Stops duplicate user-visible messages when the same outbound path runs twice (webhook retries,
double tasks, or overlapping handlers). Safe to call from any adapter or webhook wrapper.
"""

from __future__ import annotations

import hashlib
import time
from typing import Dict

# Tunable via env in config if needed later
WINDOW_SEC = 15.0

_cache: Dict[str, float] = {}


def _key(to_number: str, message: str) -> str:
    text = (message or "").strip()
    basis = f"{(to_number or '').strip()}\0{text}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:32]


def is_duplicate_outbound_text(to_number: str, message: str) -> bool:
    """
    Return True if this exact (recipient, trimmed body) was already recorded within WINDOW_SEC
    — caller should skip sending. Otherwise record timestamp and return False.
    """
    text = (message or "").strip()
    if not text:
        return False
    k = _key(to_number, text)
    now = time.time()
    stale = [x for x, ts in _cache.items() if now - ts > WINDOW_SEC * 6]
    for x in stale:
        _cache.pop(x, None)
    prev = _cache.get(k)
    if prev is not None and (now - prev) < WINDOW_SEC:
        print(
            f"⚠️ Outbound duplicate suppressed (global): same text to same recipient within "
            f"{now - prev:.1f}s (window={WINDOW_SEC}s)"
        )
        return True
    _cache[k] = now
    return False
