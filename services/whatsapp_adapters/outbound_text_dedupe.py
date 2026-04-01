"""
Process-wide guard: identical WhatsApp text to the same logical recipient within a short window.

- Normalizes recipient (digits tail) so +961..., 961..., and resolved phone from room_id share one key.
- Uses in-flight tracking + asyncio lock so two concurrent identical sends only result in one HTTP call.
- Records success timestamp only after a successful send, so failed API calls do not block retries.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from typing import Dict, Set

# Same user can legitimately get two different messages within seconds; identical body is the bug.
WINDOW_SEC = float(os.getenv("OUTBOUND_TEXT_DEDUPE_WINDOW_SEC", "25"))

_cache: Dict[str, float] = {}
_inflight: Set[str] = set()
_lock = asyncio.Lock()


def _normalize_recipient(phone_or_room: str) -> str:
    """One key per human: strip and use last N digits when phone-like; else full stripped id (room)."""
    s = (phone_or_room or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        return digits[-15:]
    return s


def _body_key(message: str) -> str:
    t = (message or "").strip()
    if not t:
        return ""
    # Collapse internal runs of whitespace so tiny formatting diffs still match
    return re.sub(r"\s+", " ", t)


def _cache_key(recipient_norm: str, body: str) -> str:
    b = _body_key(body)
    if not b:
        return ""
    basis = f"{recipient_norm}\0{b}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:32]


def _prune_stale(now: float) -> None:
    cutoff = now - WINDOW_SEC * 8
    stale = [k for k, ts in _cache.items() if ts < cutoff]
    for k in stale:
        _cache.pop(k, None)


async def should_skip_outbound_text(resolved_recipient: str, message: str) -> bool:
    """
    Call before HTTP. Returns True if this send should be skipped (duplicate or in-flight).

    resolved_recipient: already room→phone resolved when applicable (e.g. MontyMobile _get_phone_from_room_id).
    """
    rn = _normalize_recipient(resolved_recipient)
    k = _cache_key(rn, message)
    if not k:
        return False
    now = time.time()
    async with _lock:
        _prune_stale(now)
        prev = _cache.get(k)
        if prev is not None and (now - prev) < WINDOW_SEC:
            print(
                f"⚠️ Outbound duplicate suppressed (global): same text to same recipient within "
                f"{now - prev:.1f}s (window={WINDOW_SEC}s)"
            )
            return True
        if k in _inflight:
            print("⚠️ Outbound duplicate suppressed (global): identical send already in flight")
            return True
        _inflight.add(k)
    return False


async def finish_outbound_text_attempt(resolved_recipient: str, message: str, send_success: bool) -> None:
    """Call after HTTP completes (success or failure)."""
    rn = _normalize_recipient(resolved_recipient)
    k = _cache_key(rn, message)
    if not k:
        return
    now = time.time()
    async with _lock:
        _inflight.discard(k)
        if send_success:
            _cache[k] = now
