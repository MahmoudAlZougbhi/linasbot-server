"""Central provider concurrency / rate-limit controller with tenant fairness."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderDecision:
    allowed: bool
    retry_after_seconds: float
    reason: str


PRIORITY_WEIGHTS = {
    "owner_mobile": 1,
    "customer_conversation": 2,
    "request_notification": 3,
    "background": 4,
}


class ProviderLimiter:
    """
    Shared Redis fixed-window + inflight caps.

    Provider throttling must increase queue latency, not crash or drop events.
    """

    def __init__(self, redis_client: Any | None = None, *, prefix: str | None = None) -> None:
        self._redis = redis_client
        self._prefix = (prefix or os.getenv("LINAS_PROVIDER_LIMIT_PREFIX") or "linas:prov").strip()

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            raise RuntimeError("ProviderLimiter requires REDIS_URL")
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        return self._redis

    def _limit(self, env_key: str, default: int) -> int:
        try:
            return max(0, int(os.getenv(env_key) or str(default)))
        except ValueError:
            return default

    def openai_rpm(self) -> int:
        return self._limit("LINAS_OPENAI_RPM", 60)

    def openai_inflight(self) -> int:
        return self._limit("LINAS_OPENAI_INFLIGHT", 8)

    def meta_rpm(self) -> int:
        return self._limit("LINAS_META_RPM", 120)

    def tenant_inflight_cap(self) -> int:
        return self._limit("LINAS_TENANT_PROVIDER_INFLIGHT", 4)

    def check(
        self,
        *,
        provider: str,
        tenant_id: str,
        priority: str = "customer_conversation",
    ) -> ProviderDecision:
        r = self._client()
        tid = (tenant_id or "unknown").strip() or "unknown"
        prov = (provider or "unknown").strip().lower()
        minute = int(time.time() // 60)

        rpm = self.openai_rpm() if prov == "openai" else self.meta_rpm() if prov.startswith("meta") else 60
        rpm_key = f"{self._prefix}:rpm:{prov}:{minute}"
        count = int(r.incr(rpm_key))
        if count == 1:
            r.expire(rpm_key, 120)
        if rpm > 0 and count > rpm:
            # Jittered backoff so workers do not herd.
            delay = 1.0 + random.random() * 1.5
            return ProviderDecision(False, delay, "provider_rpm")

        inflight_cap = self.openai_inflight() if prov == "openai" else self._limit("LINAS_META_INFLIGHT", 16)
        inflight_key = f"{self._prefix}:inflight:{prov}"
        inflight = int(r.get(inflight_key) or 0)
        if inflight_cap > 0 and inflight >= inflight_cap:
            return ProviderDecision(False, 0.5 + random.random(), "provider_inflight")

        t_key = f"{self._prefix}:tenant_inflight:{prov}:{tid}"
        t_inflight = int(r.get(t_key) or 0)
        if t_inflight >= self.tenant_inflight_cap():
            # Lower priority classes wait longer (fairness / anti-starve via soft delay).
            weight = PRIORITY_WEIGHTS.get(priority, 2)
            return ProviderDecision(False, 0.25 * weight + random.random() * 0.25, "tenant_inflight")

        return ProviderDecision(True, 0.0, "ok")

    def acquire_inflight(self, *, provider: str, tenant_id: str) -> None:
        r = self._client()
        prov = (provider or "unknown").strip().lower()
        tid = (tenant_id or "unknown").strip() or "unknown"
        pipe = r.pipeline()
        pipe.incr(f"{self._prefix}:inflight:{prov}")
        pipe.expire(f"{self._prefix}:inflight:{prov}", 3600)
        pipe.incr(f"{self._prefix}:tenant_inflight:{prov}:{tid}")
        pipe.expire(f"{self._prefix}:tenant_inflight:{prov}:{tid}", 3600)
        pipe.execute()

    def release_inflight(self, *, provider: str, tenant_id: str) -> None:
        r = self._client()
        prov = (provider or "unknown").strip().lower()
        tid = (tenant_id or "unknown").strip() or "unknown"
        for key in (
            f"{self._prefix}:inflight:{prov}",
            f"{self._prefix}:tenant_inflight:{prov}:{tid}",
        ):
            try:
                val = int(r.decr(key))
                if val < 0:
                    r.set(key, 0, ex=3600)
            except Exception:
                pass

    def backoff_seconds(self, attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
        exp = min(cap, base * (2 ** max(0, min(attempt, 8))))
        return exp + random.random() * 0.5
