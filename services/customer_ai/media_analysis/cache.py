"""Shared Redis cache for one-shot post/reel media analysis."""

from __future__ import annotations

import json
import os
from typing import Any

_PREFIX = (os.getenv("LINAS_POST_MEDIA_PREFIX") or "linas:post_media").strip() or "linas:post_media"
_SUCCESS_TTL_SEC = max(3600, int(os.getenv("LINAS_POST_MEDIA_TTL_SEC") or str(30 * 86400)))
_FAIL_TTL_SEC = 900
_LOCK_TTL_SEC = 180
_TEST_CLIENT: Any | None = None


def set_post_media_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _safe(part: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in part)[:180]


def analysis_key(*, tenant_id: str, post_id: str) -> str:
    return f"{_PREFIX}:{_safe(tenant_id)}:{_safe(post_id)}"


def lock_key(*, tenant_id: str, post_id: str) -> str:
    return f"{_PREFIX}:lock:{_safe(tenant_id)}:{_safe(post_id)}"


def get_analysis(*, tenant_id: str, post_id: str) -> dict[str, Any] | None:
    client = _client()
    if client is None or not tenant_id or not post_id:
        return None
    raw = client.get(analysis_key(tenant_id=tenant_id, post_id=post_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def put_analysis(*, tenant_id: str, post_id: str, payload: dict[str, Any]) -> bool:
    client = _client()
    if client is None or not tenant_id or not post_id:
        return False
    status = str(payload.get("status") or "")
    ttl = _SUCCESS_TTL_SEC if status == "ok" else _FAIL_TTL_SEC
    try:
        client.set(
            analysis_key(tenant_id=tenant_id, post_id=post_id),
            json.dumps(payload, separators=(",", ":")),
            ex=ttl,
        )
        return True
    except Exception:
        return False


def acquire_lock(*, tenant_id: str, post_id: str) -> bool:
    client = _client()
    if client is None or not tenant_id or not post_id:
        return True
    key = lock_key(tenant_id=tenant_id, post_id=post_id)
    try:
        ok = client.set(key, "1", nx=True, ex=_LOCK_TTL_SEC)
        return bool(ok)
    except TypeError:
        if client.get(key):
            return False
        client.set(key, "1", ex=_LOCK_TTL_SEC)
        return True
    except Exception:
        return True


def release_lock(*, tenant_id: str, post_id: str) -> None:
    client = _client()
    if client is None or not tenant_id or not post_id:
        return
    try:
        client.delete(lock_key(tenant_id=tenant_id, post_id=post_id))
    except Exception:
        return
