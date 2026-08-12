"""Shared Redis claim helper for multi-instance webhook/idempotency short windows."""

from __future__ import annotations

import os
from typing import Any


class RedisClaimStore:
    """SET NX EX claims. Returns True when this caller owns the claim."""

    def __init__(self, redis_client: Any | None = None, *, prefix: str | None = None) -> None:
        self._redis = redis_client
        self._prefix = (prefix or os.getenv("LINAS_CLAIM_PREFIX") or "linas:claim").strip()

    def _client(self) -> Any | None:
        if self._redis is not None:
            return self._redis
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            return None
        import redis

        try:
            client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            client.ping()
            self._redis = client
            return client
        except Exception:
            self._redis = None
            return None

    def try_claim(self, namespace: str, key: str, *, ttl_seconds: float) -> bool | None:
        """
        True = claimed here; False = duplicate; None = Redis unavailable (caller decides).
        """
        client = self._client()
        if client is None:
            return None
        safe_ns = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)[:64]
        safe_key = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in key)[:200]
        redis_key = f"{self._prefix}:{safe_ns}:{safe_key}"
        ok = bool(client.set(redis_key, "1", nx=True, ex=max(1, int(ttl_seconds))))
        return ok


_shared_claims = RedisClaimStore()


def redis_try_claim(namespace: str, key: str, *, ttl_seconds: float) -> bool | None:
    return _shared_claims.try_claim(namespace, key, ttl_seconds=ttl_seconds)
