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
import unicodedata
from typing import Dict, Optional, Set

from utils.phone_utils import phone_match_key

# Same user can legitimately get two different messages within seconds; identical body is the bug.
WINDOW_SEC = float(os.getenv("OUTBOUND_TEXT_DEDUPE_WINDOW_SEC", "90"))

_cache: Dict[str, float] = {}
_inflight: Set[str] = set()
_lock = asyncio.Lock()


def _normalize_recipient(phone_or_room: str) -> str:
    """One stable key per human: prefer E.164 digits via phone_match_key; else room/non-phone id."""
    s = (phone_or_room or "").strip()
    if not s:
        return ""
    pk = phone_match_key(s)
    if pk:
        return pk
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        return digits[-15:]
    return s


_ZW_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")


def normalize_text_body_for_dedupe(message: str) -> str:
    """NFKC + strip ZWSP + collapse whitespace; shared by inbound webhook fp and outbound dedupe."""
    t = (message or "").strip()
    if not t:
        return ""
    t = unicodedata.normalize("NFKC", t)
    t = _ZW_RE.sub("", t)
    return re.sub(r"\s+", " ", t)


def _body_key(message: str) -> str:
    return normalize_text_body_for_dedupe(message)


def outbound_fingerprint(recipient: str, message: str, phone_hint: Optional[str] = None) -> str:
    """
    Same key as should_skip_outbound_text uses after optional phone hint (canonical number).
    Use for per-handler duplicate suppression aligned with global dedupe.
    """
    hint = (phone_hint or "").strip()
    if hint:
        pk = phone_match_key(hint)
        if pk:
            rn = pk
        else:
            rn = _normalize_recipient(recipient)
    else:
        rn = _normalize_recipient(recipient)
    k = _cache_key(rn, message)
    return k or ""


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
