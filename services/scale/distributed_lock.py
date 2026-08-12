"""Distributed lock for singleton schedulers / once-per-cluster jobs."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class LockLease:
    name: str
    key: str
    token: str
    ttl_seconds: int


class DistributedLock:
    """Redis SET NX EX lock. Fail closed when Redis unavailable and required."""

    def __init__(self, redis_client: Any | None = None, *, prefix: str | None = None) -> None:
        self._redis = redis_client
        self._prefix = (prefix or os.getenv("LINAS_DIST_LOCK_PREFIX") or "linas:lock").strip()

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            raise RuntimeError("DistributedLock requires REDIS_URL")
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        return self._redis

    def try_acquire(self, name: str, *, ttl_seconds: int = 60) -> LockLease | None:
        token = uuid.uuid4().hex
        key = f"{self._prefix}:{name}"
        ok = bool(self._client().set(key, token, nx=True, ex=max(5, int(ttl_seconds))))
        if not ok:
            return None
        return LockLease(name=name, key=key, token=token, ttl_seconds=max(5, int(ttl_seconds)))

    def release(self, lease: LockLease) -> None:
        r = self._client()
        try:
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

    def run_singleton(self, name: str, fn: Any, *, ttl_seconds: int = 60) -> bool:
        """Run fn only if lock acquired. Returns True when fn ran."""
        lease = self.try_acquire(name, ttl_seconds=ttl_seconds)
        if lease is None:
            return False
        try:
            fn()
            return True
        finally:
            self.release(lease)

    def hold_heartbeat(self, lease: LockLease, *, every_seconds: float = 10.0) -> None:
        """Extend TTL while holding (caller runs in loop)."""
        time.sleep(max(0.5, every_seconds))
        r = self._client()
        try:
            if r.get(lease.key) == lease.token:
                r.expire(lease.key, lease.ttl_seconds)
        except Exception:
            pass
