"""Provider 429 / RPM cap must not cause worker scale-up."""

from __future__ import annotations

import fakeredis

from services.scale.autoscale_signal import recommend
from services.scale.provider_limiter import ProviderLimiter


def test_openai_rpm_blocks_and_autoscale_holds() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    limiter = ProviderLimiter(redis_client=fake)
    blocked = None
    for _ in range(70):
        blocked = limiter.check(provider="openai", tenant_id="t1")
        if not blocked.allowed:
            break
    assert blocked is not None
    assert blocked.allowed is False
    rec = recommend(
        current_api=2,
        current_workers=8,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=4.0,
        provider_limited=True,
    )
    assert rec.action == "hold"
    assert rec.worker_replicas == 8
