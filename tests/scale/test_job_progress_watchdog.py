"""Progress watchdog: stuck vs long-running vs dead worker, without a second lease system."""

from __future__ import annotations

import time

import fakeredis

from services.ai_reply_lifecycle import begin_turn, persist_generated_reply
from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.delivery_ledger import begin_send, set_delivery_redis_for_tests
from services.scale.delivery_ledger import snapshot as delivery_snapshot
from services.scale.job_progress import bind_job, mark_stage, set_progress_redis_for_tests, unbind_job
from services.scale.job_progress_watchdog import classify_progress, scan_queue
from services.scale.turn_store import set_turn_redis_for_tests


def teardown_function() -> None:
    set_progress_redis_for_tests(None)
    set_delivery_redis_for_tests(None)
    set_turn_redis_for_tests(None)
    unbind_job()


def _backend(monkeypatch) -> tuple[RedisQueueBackend, object]:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    monkeypatch.setenv("LINAS_PROGRESS_GRACE_SEC", "1")
    monkeypatch.setenv("LINAS_PROGRESS_LUNA_STUCK_SEC", "2")
    monkeypatch.setenv("LINAS_PROGRESS_TERA_STUCK_SEC", "2")
    monkeypatch.setenv("LINAS_PROGRESS_DELIVERY_STUCK_SEC", "2")
    monkeypatch.setenv("LINAS_PROGRESS_MAX_STUCK", "3")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_progress_redis_for_tests(fake)
    set_delivery_redis_for_tests(fake)
    set_turn_redis_for_tests(fake)
    return RedisQueueBackend(), fake


def _claim(backend: RedisQueueBackend, *, payload: dict | None = None) -> QueueJob:
    job = QueueJob.new(
        queue="high_priority",
        job_type="combine_flush",
        tenant_id="t1",
        payload=payload or {},
    )
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert claimed is not None
    bind_job(claimed, redis=backend._r, worker_id="w-live")
    mark_stage("processing")
    return claimed


def test_long_job_with_fresh_progress_is_not_stuck() -> None:
    now = 1_000_000.0
    verdict = classify_progress(
        lease_exists=True,
        status="processing",
        progress=None,
        now=now + 180.0,
        last_progress_at=now + 179.0,
        stage="luna_started",
    )
    assert verdict.kind == "healthy"


def test_three_minute_luna_below_provider_timeout_is_not_stuck(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_PROGRESS_LUNA_STUCK_SEC", "600")
    monkeypatch.setenv("LINAS_PROGRESS_GRACE_SEC", "15")
    now = 2_000_000.0
    verdict = classify_progress(
        lease_exists=True,
        status="processing",
        progress=None,
        now=now + 180.0,
        last_progress_at=now,
        stage="luna_started",
    )
    assert verdict.kind == "healthy"


def test_event_loop_lag_within_grace_is_not_stuck(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_PROGRESS_LUNA_STUCK_SEC", "5")
    monkeypatch.setenv("LINAS_PROGRESS_GRACE_SEC", "15")
    now = 3_000_000.0
    verdict = classify_progress(
        lease_exists=True,
        status="processing",
        progress=None,
        now=now + 12.0,
        last_progress_at=now,
        stage="luna_started",
    )
    assert verdict.kind == "false_stuck_prevented"


def test_dead_worker_uses_lease_path_not_stuck() -> None:
    verdict = classify_progress(
        lease_exists=False,
        status="processing",
        progress=None,
        now=time.time(),
        last_progress_at=time.time() - 30,
        stage="luna_started",
    )
    assert verdict.kind == "dead_worker"


def test_completed_job_is_ignored() -> None:
    verdict = classify_progress(
        lease_exists=True,
        status="completed",
        progress=None,
        now=time.time(),
        last_progress_at=time.time() - 10_000,
        stage="luna_started",
    )
    assert verdict.kind == "ignore_terminal"


def test_hung_luna_is_stuck_and_recovered(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    claimed = _claim(backend)
    mark_stage("luna_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={"last_progress_at": str(time.time() - 30), "stage_started_at": str(time.time() - 30)},
    )
    stats = scan_queue(backend, "high_priority")
    assert stats["stuck"] == 1
    assert stats["recovered"] == 1
    stored = backend.get(claimed.id)
    assert stored is not None
    assert stored.status == "queued"
    assert backend.complete(claimed) in {"stale_owner", "not_processing"}


def test_hung_tera_is_detected(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    claimed = _claim(backend)
    mark_stage("tera_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={"last_progress_at": str(time.time() - 30), "current_stage": "tera_started"},
    )
    stats = scan_queue(backend, "high_priority")
    assert stats["stuck"] == 1
    assert backend.get(claimed.id).status in {"queued", "dead"}


def test_delivery_unknown_does_not_begin_another_send(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-d", claim_key_basis="c-d")
    persist_generated_reply(turn.logical_reply_id, reply_text="saved")
    claimed = _claim(backend, payload={"_logical_reply_id": turn.logical_reply_id})
    begin_send(turn.logical_reply_id)
    mark_stage("delivery_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={"last_progress_at": str(time.time() - 30), "current_stage": "delivery_started"},
    )
    scan_queue(backend, "high_priority")
    assert delivery_snapshot(turn.logical_reply_id)["state"] == "unknown"
    from services.scale.delivery_ledger import begin_send as begin_again

    assert begin_again(turn.logical_reply_id) == "skip_unknown"


def test_watchdog_and_worker_cannot_both_win(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    claimed = _claim(backend)
    mark_stage("luna_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={"last_progress_at": str(time.time() - 30), "current_stage": "luna_started"},
    )
    scan_queue(backend, "high_priority")
    result = backend.complete(claimed)
    assert result in {"stale_owner", "not_processing"}
    stored = backend.get(claimed.id)
    assert stored is not None
    assert stored.status != "completed"


def test_stuck_recovery_reuses_saved_ai(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-s", claim_key_basis="c-s")
    persist_generated_reply(turn.logical_reply_id, reply_text="already generated")
    claimed = _claim(
        backend,
        payload={"_logical_reply_id": turn.logical_reply_id, "_claim_key_basis": "c-s"},
    )
    mark_stage("luna_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={"last_progress_at": str(time.time() - 30), "current_stage": "luna_started"},
    )
    scan_queue(backend, "high_priority")
    stored = backend.get(claimed.id)
    assert stored is not None
    assert "resume_saved_ai" in str(stored.last_error or "")
    from services.ai_reply_lifecycle import find_pending_delivery_turn

    pending = find_pending_delivery_turn(claim_key_basis="c-s")
    assert pending is not None
    assert pending.generated_reply == "already generated"


def test_repeated_stuck_goes_to_dlq(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_PROGRESS_MAX_STUCK", "1")
    backend, _fake = _backend(monkeypatch)
    claimed = _claim(backend, payload={})
    claimed.max_attempts = 1
    backend._save(claimed)
    mark_stage("luna_started")
    backend._r.hset(
        f"linas:q:prog:{claimed.id}",
        mapping={
            "last_progress_at": str(time.time() - 30),
            "current_stage": "luna_started",
            "stuck_count": "0",
        },
    )
    stats = scan_queue(backend, "high_priority")
    assert stats["dlq"] == 1 or backend.get(claimed.id).status == "dead"
    dlq = backend._r.lrange(backend._k("dlq", "high_priority"), 0, -1) or []
    assert claimed.id in dlq or backend.get(claimed.id).status == "dead"


def test_watchdog_does_not_touch_completed(monkeypatch) -> None:
    backend, _fake = _backend(monkeypatch)
    claimed = _claim(backend)
    assert backend.complete(claimed).startswith("ok")
    stats = scan_queue(backend, "high_priority")
    assert stats["stuck"] == 0
    assert backend.get(claimed.id).status == "completed"
