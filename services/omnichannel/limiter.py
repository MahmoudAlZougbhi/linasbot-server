"""Distributed provider limiter with account keys, cooldowns, and inflight enter/exit."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any

from services.omnichannel.backoff import delay_for_provider
from services.omnichannel.headers import parse_retry_after_seconds, usage_snapshot
from services.scale.provider_limiter import ProviderDecision, ProviderLimiter


class DistributedProviderLimiter:
    def __init__(self, redis_client: Any | None = None, *, inner: ProviderLimiter | None = None) -> None:
        self._inner = inner or ProviderLimiter(redis_client)
        self._redis = redis_client

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        return self._inner._client()  # noqa: SLF001 — shared Redis from the existing limiter

    def _cooldown_key(self, *, provider: str, account_id: str, endpoint: str) -> str:
        prefix = self._inner._prefix  # noqa: SLF001
        acc = (account_id or "app").strip() or "app"
        ep = (endpoint or "default").strip() or "default"
        return f"{prefix}:cooldown:{provider}:{acc}:{ep}"

    def record_throttle(
        self,
        *,
        provider: str,
        account_id: str = "",
        endpoint: str = "default",
        headers: Mapping[str, Any] | None = None,
        retry_after_seconds: float | None = None,
        attempt: int = 0,
    ) -> float:
        delay = retry_after_seconds
        if delay is None:
            delay = parse_retry_after_seconds(headers)
        if delay is None:
            delay = delay_for_provider(attempt=attempt, headers=headers)
        delay = max(0.05, float(delay))
        r = self._client()
        r.set(
            self._cooldown_key(provider=provider, account_id=account_id, endpoint=endpoint),
            "1",
            ex=max(1, int(math.ceil(delay))),
        )
        usage_snapshot(headers, provider=provider)
        return delay

    def record_tokens(self, *, provider: str, tokens: int) -> None:
        if tokens <= 0:
            return
        r = self._client()
        prefix = self._inner._prefix  # noqa: SLF001
        minute = int(time.time() // 60)
        key = f"{prefix}:tpm:{provider}:{minute}"
        count = int(r.incrby(key, int(tokens)))
        if count == int(tokens):
            r.expire(key, 120)
        cap = self._inner._limit("LINAS_OPENAI_TPM", 200_000)  # noqa: SLF001
        if cap > 0 and count > cap:
            r.set(f"{prefix}:cooldown:{provider}:app:tokens", "1", ex=5)

    def try_enter(
        self,
        *,
        provider: str,
        tenant_id: str,
        account_id: str = "",
        endpoint: str = "default",
        priority: str = "customer_conversation",
    ) -> ProviderDecision:
        r = self._client()
        cooldown = self._cooldown_key(provider=provider, account_id=account_id, endpoint=endpoint)
        if r.get(cooldown):
            ttl = int(r.ttl(cooldown) or 1)
            return ProviderDecision(False, max(0.05, float(ttl)), "provider_retry_after")
        decision = self._inner.check(provider=provider, tenant_id=tenant_id, priority=priority)
        if not decision.allowed:
            return decision
        self._inner.acquire_inflight(provider=provider, tenant_id=tenant_id)
        return ProviderDecision(True, 0.0, "ok")

    def exit(self, *, provider: str, tenant_id: str) -> None:
        self._inner.release_inflight(provider=provider, tenant_id=tenant_id)
