"""Unit tests for scale primitives (fakeredis, no live providers)."""

from __future__ import annotations

import fakeredis
import pytest

from services.scale.conversation_lock import ConversationLock, conversation_partition_key
from services.scale.distributed_lock import DistributedLock
from services.scale.provider_limiter import ProviderLimiter
from services.scale.redis_claims import RedisClaimStore
from services.scale.shutdown import ShutdownCoordinator


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_conversation_partition_stable():
    a = conversation_partition_key(tenant_id="t1", channel="IG", external_conversation_id="c1")
    b = conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id="c1")
    c = conversation_partition_key(tenant_id="t2", channel="ig", external_conversation_id="c1")
    assert a == b
    assert a != c


def test_conversation_lock_exclusive(redis_client):
    lock = ConversationLock(redis_client)
    key = conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id="x")
    lease1 = lock.try_acquire(key, ttl_seconds=30)
    lease2 = lock.try_acquire(key, ttl_seconds=30)
    assert lease1 is not None
    assert lease2 is None
    lock.release(lease1)
    lease3 = lock.try_acquire(key, ttl_seconds=30)
    assert lease3 is not None
    lock.release(lease3)


def test_distributed_lock_singleton(redis_client):
    lock = DistributedLock(redis_client)
    ran = {"n": 0}

    def tick() -> None:
        ran["n"] += 1

    assert lock.run_singleton("job-a", tick, ttl_seconds=30) is True
    # Still held? run_singleton releases after fn — second should also run.
    assert lock.run_singleton("job-a", tick, ttl_seconds=30) is True
    assert ran["n"] == 2
    lease = lock.try_acquire("job-b", ttl_seconds=30)
    assert lease is not None
    assert lock.try_acquire("job-b", ttl_seconds=30) is None
    lock.release(lease)


def test_provider_limiter_blocks_rpm(redis_client, monkeypatch):
    monkeypatch.setenv("LINAS_OPENAI_RPM", "5")
    monkeypatch.setenv("LINAS_OPENAI_INFLIGHT", "100")
    monkeypatch.setenv("LINAS_TENANT_PROVIDER_INFLIGHT", "100")
    limiter = ProviderLimiter(redis_client)
    allowed = 0
    blocked = 0
    for _ in range(12):
        d = limiter.check(provider="openai", tenant_id="t1")
        if d.allowed:
            allowed += 1
        else:
            blocked += 1
            assert d.reason == "provider_rpm"
    assert allowed == 5
    assert blocked == 7


def test_redis_claims_multi_tenant_isolation(redis_client):
    store = RedisClaimStore(redis_client)
    assert store.try_claim("ns", "t1:mid", ttl_seconds=30) is True
    assert store.try_claim("ns", "t1:mid", ttl_seconds=30) is False
    assert store.try_claim("ns", "t2:mid", ttl_seconds=30) is True


def test_shutdown_drain_rejects_new_work():
    c = ShutdownCoordinator()
    assert c.track_http_enter() is True
    c.track_http_exit()
    c.begin_drain()
    assert c.track_http_enter() is False
    assert c.accept_queue_work is False


def test_multi_tenant_rate_limit_isolation(redis_client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    from services.rate_limit_service import RateLimitService

    svc = RateLimitService(backend="redis", redis_client=redis_client)
    for _ in range(3):
        ok, _ = svc.hit("tenant:a:login", limit=3, window_seconds=60)
        assert ok
    ok, _ = svc.hit("tenant:a:login", limit=3, window_seconds=60)
    assert ok is False
    ok_b, _ = svc.hit("tenant:b:login", limit=3, window_seconds=60)
    assert ok_b is True
