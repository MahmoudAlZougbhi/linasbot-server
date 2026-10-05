"""Pause scheduled Firestore scans after a quota error.

Live customer replies are not routed through this helper. A quota failure
backs the watchdog off; a later successful scan clears it. The clock is shared
through Redis when Redis is up, so both production nodes pause together.
"""

from __future__ import annotations

import time
from typing import Any

_MAX_DELAY_SECONDS = 900
_local_until = 0.0
_level = 0


def is_quota_error(exc: BaseException | None) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = f"{type(current).__name__} {current}".lower()
        if "429" in text or "quota" in text or "resource exhausted" in text or "resource_exhausted" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


def _redis() -> Any | None:
    try:
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            return None
        import redis

        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.4, socket_timeout=0.4)
        client.ping()
        return client
    except Exception:
        return None


def _key() -> str:
    import os

    prefix = (os.getenv("LINAS_CLAIM_PREFIX") or "linas:claim").strip()
    return f"{prefix}:firestore_quota_backoff"


def quota_backoff_active(now: float | None = None) -> bool:
    moment = time.time() if now is None else float(now)
    client = _redis()
    if client is not None:
        try:
            raw = client.get(_key())
            if raw:
                return float(raw) > moment
        except Exception:
            pass
    return _local_until > moment


def note_quota_failure(now: float | None = None) -> float:
    """Arm the next delay: 60s, then 120, 240, 480, capped at 15 minutes."""
    global _level, _local_until
    moment = time.time() if now is None else float(now)
    _level = min(_level + 1, 5)
    delay = min(_MAX_DELAY_SECONDS, 60 * (2 ** (_level - 1)))
    until = moment + delay
    _local_until = until
    client = _redis()
    if client is not None:
        try:
            client.set(_key(), str(until), ex=int(delay) + 5)
        except Exception:
            pass
    return until


def note_quota_success() -> None:
    global _level, _local_until
    _level = 0
    _local_until = 0.0
    client = _redis()
    if client is not None:
        try:
            client.delete(_key())
        except Exception:
            pass


def note_quota_result(exc: BaseException | None) -> None:
    if exc is None:
        note_quota_success()
    elif is_quota_error(exc):
        note_quota_failure()
