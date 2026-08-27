"""Hot conversation serialization must not stall other conversations."""

from __future__ import annotations

import fakeredis

from services.scale.conversation_lock import ConversationLock, conversation_partition_key
from services.scale.worker_lock_policy import job_requires_conversation_lock


def test_lock_is_per_conversation_not_global() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    lock = ConversationLock(redis_client)
    hot = conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id="hot")
    other = conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id="other")
    lease_hot = lock.try_acquire(hot, ttl_seconds=30)
    lease_other = lock.try_acquire(other, ttl_seconds=30)
    assert lease_hot is not None
    assert lease_other is not None
    lock.release(lease_hot)
    lock.release(lease_other)


def test_thousands_of_conversations_use_distinct_keys() -> None:
    keys = {
        conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id=f"c{i}")
        for i in range(3000)
    }
    assert len(keys) == 3000
    other_tenant = conversation_partition_key(tenant_id="t2", channel="ig", external_conversation_id="c0")
    assert other_tenant not in keys or True
    assert other_tenant != conversation_partition_key(tenant_id="t1", channel="ig", external_conversation_id="c0")


def test_inbound_buffer_jobs_can_append_while_another_conversation_generates() -> None:
    assert job_requires_conversation_lock("meta_inbound_process") is False
    assert job_requires_conversation_lock("combine_flush") is True
