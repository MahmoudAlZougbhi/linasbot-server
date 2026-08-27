"""Single scaler leader so two controllers cannot create nodes together."""

from __future__ import annotations

import os
import uuid
from typing import Any

_PREFIX = (os.getenv("LINAS_SCALE_LOCK_PREFIX") or "linas:scale").strip() or "linas:scale"
_TEST_CLIENT: Any | None = None
_OWNER = uuid.uuid4().hex[:12]


def set_leader_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def acquire_leader(name: str, *, ttl_seconds: int = 15) -> bool:
    client = _client()
    if client is None:
        return False
    key = f"{_PREFIX}:leader:{name}"
    try:
        return bool(client.set(key, _OWNER, nx=True, ex=max(5, int(ttl_seconds))))
    except Exception:
        return False


def release_leader(name: str) -> None:
    client = _client()
    if client is None:
        return
    key = f"{_PREFIX}:leader:{name}"
    try:
        current = client.get(key)
        if str(current or "") == _OWNER:
            client.delete(key)
    except Exception:
        return
