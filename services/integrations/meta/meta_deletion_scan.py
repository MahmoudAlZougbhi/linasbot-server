"""One pending-code scan for both deletion nodes.

The node that wins the lock reads the limited query and stores the codes.
The peer acks those same codes with point reads and does not scan the collection.
"""

from __future__ import annotations

import json
from typing import Any

_KEY = "linas:claim:meta_deletion_pending_codes"
_TTL_SECONDS = 70


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


def store_pending_codes(codes: list[str]) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(_KEY, json.dumps(list(codes)), ex=_TTL_SECONDS)
    except Exception:
        return


def load_pending_codes() -> list[str] | None:
    """Return the stored codes, or None when this minute's scan is not published yet."""
    client = _redis()
    if client is None:
        return []
    try:
        raw = client.get(_KEY)
    except Exception:
        return []
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return [str(item) for item in payload if str(item).strip()]
