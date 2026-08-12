"""Per-conversation ordering lock (tenant + channel + external conversation id)."""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any


def conversation_partition_key(*, tenant_id: str, channel: str, external_conversation_id: str) -> str:
    tid = (tenant_id or "").strip() or "unknown"
    ch = (channel or "").strip().lower() or "unknown"
    ext = (external_conversation_id or "").strip() or "unknown"
    return f"{tid}:{ch}:{ext}"


@dataclass
class ConversationLease:
    key: str
    token: str
    ttl_seconds: int


class ConversationLock:
    """
    Prevent two AI workers from replying in the same conversation concurrently.

    Different conversations proceed in parallel. Requires Redis for multi-instance safety.
    """

    def __init__(self, redis_client: Any | None = None, *, prefix: str | None = None) -> None:
        self._redis = redis_client
        self._prefix = (prefix or os.getenv("LINAS_CONV_LOCK_PREFIX") or "linas:convlock").strip()

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            raise RuntimeError("ConversationLock requires REDIS_URL")
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        return self._redis

    def _redis_key(self, partition_key: str) -> str:
        digest = hashlib.sha256(partition_key.encode("utf-8")).hexdigest()[:40]
        return f"{self._prefix}:{digest}"

    def try_acquire(self, partition_key: str, *, ttl_seconds: int = 120) -> ConversationLease | None:
        token = uuid.uuid4().hex
        key = self._redis_key(partition_key)
        ok = bool(self._client().set(key, token, nx=True, ex=max(5, int(ttl_seconds))))
        if not ok:
            return None
        return ConversationLease(key=key, token=token, ttl_seconds=max(5, int(ttl_seconds)))

    def refresh(self, lease: ConversationLease, *, ttl_seconds: int | None = None) -> bool:
        ttl = max(5, int(ttl_seconds or lease.ttl_seconds))
        r = self._client()
        try:
            current = r.get(lease.key)
            if current != lease.token:
                return False
            return bool(r.expire(lease.key, ttl))
        except Exception:
            return False

    def release(self, lease: ConversationLease) -> None:
        r = self._client()
        try:
            # Compare-then-delete; prefer atomic Lua when available.
            script = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
            r.eval(script, 1, lease.key, lease.token)
            return
        except Exception:
            pass
        try:
            if r.get(lease.key) == lease.token:
                r.delete(lease.key)
        except Exception:
            pass

    def is_held(self, partition_key: str) -> bool:
        return bool(self._client().exists(self._redis_key(partition_key)))

    def wait_acquire(
        self,
        partition_key: str,
        *,
        ttl_seconds: int = 120,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.05,
    ) -> ConversationLease | None:
        deadline = time.time() + max(0.1, timeout_seconds)
        while time.time() < deadline:
            lease = self.try_acquire(partition_key, ttl_seconds=ttl_seconds)
            if lease is not None:
                return lease
            time.sleep(max(0.01, poll_seconds))
        return None
