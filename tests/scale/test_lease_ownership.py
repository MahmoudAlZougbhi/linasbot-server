"""Lease ownership: complete/fail/reclaim are token-CAS and keep completed jobs off the DLQ."""

from __future__ import annotations

import threading

import fakeredis

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.job_progress import set_progress_redis_for_tests
from services.scale.turn_store import set_turn_redis_for_tests


def teardown_function() -> None:
    set_progress_redis_for_tests(None)
    set_turn_redis_for_tests(None)


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_progress_redis_for_tests(fake)
    return RedisQueueBackend()


def _enqueue_claim(backend: RedisQueueBackend, *, worker_id: str = "w-a", **kwargs) -> QueueJob:
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"k": "v"}, **kwargs)
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id=worker_id, timeout=1)
    assert claimed is not None
    return claimed


def test_short_job_completes_once(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend)
    first = backend.complete(claimed)
    assert first.startswith("ok")
    second = backend.complete(claimed)
    assert second.startswith("already_completed")
    assert backend.claim("high_priority", worker_id="w-b", timeout=1) is None
    stored = backend.get(claimed.id)
    assert stored is not None
    assert stored.status == "completed"


def test_complete_after_lease_key_gone_still_succeeds_if_token_matches(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend)
    backend._r.delete(backend._k("lease", claimed.id))
    result = backend.complete(claimed)
    assert result.startswith("ok")
    assert backend.reclaim_expired_leases("high_priority") == 0
    assert backend.get(claimed.id).status == "completed"


def test_stale_owner_cannot_complete_after_reclaim(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    worker_a = _enqueue_claim(backend, worker_id="w-a")
    backend._r.delete(backend._k("lease", worker_a.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    worker_b = backend.claim("high_priority", worker_id="w-b", timeout=1)
    assert worker_b is not None
    assert worker_b.id == worker_a.id
    stale = backend.complete(worker_a)
    assert stale == "stale_owner"
    ok = backend.complete(worker_b)
    assert ok.startswith("ok")
    assert backend.get(worker_a.id).status == "completed"


def test_stale_owner_cannot_fail_after_new_owner_completes(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    worker_a = _enqueue_claim(backend, worker_id="w-a")
    backend._r.delete(backend._k("lease", worker_a.id))
    backend.reclaim_expired_leases("high_priority")
    worker_b = backend.claim("high_priority", worker_id="w-b", timeout=1)
    assert worker_b is not None
    assert backend.complete(worker_b).startswith("ok")
    assert backend.fail(worker_a, error="late", retry=True) is False
    assert backend.get(worker_a.id).status == "completed"
    dlq = backend._r.lrange(backend._k("dlq", "high_priority"), 0, -1) or []
    assert worker_a.id not in dlq


def test_complete_then_fail_does_not_requeue(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend)
    backend.complete(claimed)
    assert backend.fail(claimed, error="after_complete", retry=True) is False
    assert backend.get(claimed.id).status == "completed"
    assert backend.claim("high_priority", worker_id="w-z", timeout=1) is None


def test_completed_job_is_removed_from_dlq(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend)
    backend._r.lpush(backend._k("dlq", "high_priority"), claimed.id)
    result = backend.complete(claimed)
    assert result.startswith("ok")
    assert parse_dlq_count(result) >= 1 or claimed.id not in (
        backend._r.lrange(backend._k("dlq", "high_priority"), 0, -1) or []
    )
    stored = backend.get(claimed.id)
    assert stored is not None
    assert stored.status == "completed"
    leftover = backend._r.lrange(backend._k("dlq", "high_priority"), 0, -1) or []
    assert claimed.id not in leftover
    processing = backend._r.lrange(backend._k("processing", "high_priority"), 0, -1) or []
    assert claimed.id not in processing


def parse_dlq_count(result: str) -> int:
    if ":" not in result:
        return 0
    try:
        return int(result.rsplit(":", 1)[-1])
    except ValueError:
        return 0


def test_duplicate_reclaim_only_one_owner(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend, worker_id="w-dead")
    backend._r.delete(backend._k("lease", claimed.id))
    results: list[int] = []

    def _run() -> None:
        results.append(backend.reclaim_expired_leases("high_priority"))

    threads = [threading.Thread(target=_run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(results) == 1
    queued = backend._r.lrange(backend._k("queue", "high_priority"), 0, -1) or []
    delayed = backend._r.zrange(backend._k("delayed", "high_priority"), 0, -1) or []
    copies = list(queued) + list(delayed)
    assert copies.count(claimed.id) == 1
    again = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert again is not None
    third = backend.claim("high_priority", worker_id="w-other", timeout=1)
    assert third is None


def test_worker_dies_after_ai_saved_reply_is_reused(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    from services.ai_reply_lifecycle import begin_turn, find_pending_delivery_turn, persist_generated_reply
    from services.scale.turn_store import set_turn_redis_for_tests

    set_turn_redis_for_tests(backend._r)
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-ai", claim_key_basis="claim-ai")
    persist_generated_reply(turn.logical_reply_id, reply_text="do not regenerate")
    claimed = _enqueue_claim(backend, worker_id="w-dead")
    backend._r.delete(backend._k("lease", claimed.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    pending = find_pending_delivery_turn(claim_key_basis="claim-ai")
    assert pending is not None
    assert pending.generated_reply == "do not regenerate"
    live = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert live is not None
    assert backend.complete(live).startswith("ok")

    backend = _backend(monkeypatch)
    claimed = _enqueue_claim(backend)
    backend.complete(claimed)
    backend._r.lpush(backend._k("processing", "high_priority"), claimed.id)
    assert backend.reclaim_expired_leases("high_priority") == 0
    assert backend.get(claimed.id).status == "completed"
    assert backend.claim("high_priority", worker_id="w-replay", timeout=1) is None
