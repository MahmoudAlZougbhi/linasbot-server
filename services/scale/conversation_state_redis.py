"""Valkey-backed critical conversation flags for multi-node correctness.

Stores only correctness-critical cross-node fields:
- human takeover mode
- pending combine buffer (serialized text chunks)

Not a full replacement for all config.user_* dicts — remaining fields stay
process-local (SAFE_LOCAL_CACHE / ACCEPTABLE until explicit owner cutover).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PREFIX = (os.getenv("LINAS_CONV_STATE_PREFIX") or "linas:conv").strip()
_TTL_SEC = max(60, int(os.getenv("LINAS_CONV_STATE_TTL_SEC") or "86400"))


def _client() -> Any | None:
    try:
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            return None
        import redis

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        client.ping()
        return client
    except Exception:
        return None


def _key(tenant_user: str, field: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in tenant_user)[:200]
    return f"{_PREFIX}:{field}:{safe}"


def get_takeover(user_key: str) -> bool | None:
    """True/False from Redis; None if Redis unavailable."""
    client = _client()
    if client is None:
        return None
    try:
        raw = client.get(_key(user_key, "takeover"))
        if raw is None:
            return False
        return raw in {"1", "true", "True"}
    except Exception:
        return None


def set_takeover(user_key: str, enabled: bool) -> bool:
    """Return True when Redis write succeeded."""
    client = _client()
    if client is None:
        return False
    try:
        client.set(_key(user_key, "takeover"), "1" if enabled else "0", ex=_TTL_SEC)
        return True
    except Exception as exc:
        logger.warning("conv takeover redis write failed: %s", type(exc).__name__)
        return False


def get_pending_messages(user_key: str) -> list[str] | None:
    """Pending text chunks from Redis; None if unavailable."""
    client = _client()
    if client is None:
        return None
    try:
        raw = client.get(_key(user_key, "pending"))
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [str(item) for item in data]
    except Exception:
        return None


def set_pending_messages(user_key: str, messages: list[str]) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        if not messages:
            client.delete(_key(user_key, "pending"))
            return True
        client.set(_key(user_key, "pending"), json.dumps(list(messages)), ex=_TTL_SEC)
        return True
    except Exception as exc:
        logger.warning("conv pending redis write failed: %s", type(exc).__name__)
        return False
