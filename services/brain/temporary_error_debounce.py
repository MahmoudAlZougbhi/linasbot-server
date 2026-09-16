"""One temporary-error line per conversation+blocker for a short window."""

from __future__ import annotations

import hashlib
import time
from typing import Any

_TTL_SEC = 180
_LOCAL: dict[str, float] = {}
_PREFIX = "linas:brain:temp_err"


def reset_temporary_error_debounce_for_tests() -> None:
    _LOCAL.clear()


def _fingerprint(blocker: str) -> str:
    raw = (blocker or "").strip()[:240]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _key(tenant_id: str, conversation_id: str, blocker: str) -> str:
    tenant = (tenant_id or "").strip() or "_"
    conv = (conversation_id or "").strip() or "_"
    return f"{_PREFIX}:{tenant}:{conv}:{_fingerprint(blocker)}"


def _client() -> Any | None:
    try:
        from services.scale.redis_pool import redis_client

        return redis_client()
    except Exception:
        return None


def should_silence_repeat_temporary_error(
    *,
    tenant_id: str,
    conversation_id: str,
    blocker: str,
    now: float | None = None,
) -> bool:
    """True when the same blocker already produced a temporary-error in this window.

    First occurrence is sent. Repeats within TTL are silenced (empty outbound).
    """
    if not (blocker or "").strip():
        return False
    key = _key(tenant_id, conversation_id, blocker)
    stamp = float(now if now is not None else time.monotonic())
    client = _client()
    if client is not None:
        try:
            stored = client.set(key, "1", ex=_TTL_SEC, nx=True)
            if stored:
                _LOCAL[key] = stamp
                return False
            return True
        except Exception:
            pass
    last = _LOCAL.get(key)
    if last is not None and stamp - last < _TTL_SEC:
        return True
    _LOCAL[key] = stamp
    return False
