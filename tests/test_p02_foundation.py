"""P02 foundation stays off until a flag selects the new path."""

from __future__ import annotations

import tempfile
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from services.platform.brain_build_timeout import expire_building
from services.platform.feature_flags import flag_value
from services.platform.health_checks import ready_payload
from services.platform.pg_jobs import (
    PgDurableQueue,
    accept_inbound,
    claim_outbound,
    ensure_schema,
    set_engine_for_tests,
)
from services.platform.pg_worker import release_open_lease, run_once
from services.platform.scheduler_leader import release_leader, try_acquire_leader
from services.queues.models import QueueJob


def _engine():
    path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    path.close()
    engine = create_engine(
        f"sqlite:///{path.name}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    ensure_schema(engine)
    set_engine_for_tests(engine)
    return engine


def test_flags_default_to_the_old_path(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_FLAG_QUEUE_BACKEND", raising=False)
    assert flag_value("queue_backend") == "redis"
    assert flag_value("vector_backend") == "current"
    assert flag_value("webhook_ingest") == "legacy"


def test_lease_release_lets_another_worker_run_once() -> None:
    engine = _engine()
    queue = PgDurableQueue(engine)
    job = queue.enqueue(
        QueueJob.new(queue="maintenance", job_type="scheduler_tick", tenant_id="qa-staging", payload={"n": 1})
    )
    first = queue.claim("maintenance", worker_id="worker-a", timeout=30)
    assert first is not None and first.id == job.id
    from services.platform.pg_worker import _OPEN

    _OPEN["job"] = first
    release_open_lease(queue, worker_id="worker-a")
    again = queue.claim("maintenance", worker_id="worker-b", timeout=5)
    assert again is not None
    assert again.id == job.id


def test_poison_job_lands_in_the_dlq() -> None:
    engine = _engine()
    queue = PgDurableQueue(engine)
    queue.enqueue(
        QueueJob.new(
            queue="maintenance",
            job_type="scheduler_tick",
            tenant_id="qa-staging",
            payload={},
            max_attempts=1,
        )
    )

    def boom(_job: QueueJob) -> None:
        raise RuntimeError("poison")

    assert run_once(queue, queue_name="maintenance", worker_id="worker-a", handler=boom) is True
    assert queue.list_dlq()[0]["reason"] == "poison"
    assert queue.claim("maintenance", worker_id="worker-b") is None


def test_five_pods_send_one_outbound() -> None:
    engine = _engine()
    results: list[bool] = []

    def once() -> None:
        results.append(claim_outbound(engine, idempotency_key="same-key", tenant_id="qa-staging", provider="mock"))

    threads = [threading.Thread(target=once) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1


def test_duplicate_webhook_inserts_one_job() -> None:
    engine = _engine()
    first = accept_inbound(
        engine,
        provider="meta",
        provider_event_id="evt-1",
        tenant_id="qa-staging",
        payload={"ok": True},
    )
    second = accept_inbound(
        engine,
        provider="meta",
        provider_event_id="evt-1",
        tenant_id="qa-staging",
        payload={"ok": True},
    )
    queue = PgDurableQueue(engine)
    assert first is True
    assert second is False
    assert queue.depth()["webhook_process"] == 1


def test_only_one_scheduler_leader() -> None:
    engine = _engine()
    assert try_acquire_leader(engine, name="scheduler", owner="pod-a") is True
    assert try_acquire_leader(engine, name="scheduler", owner="pod-b") is False
    release_leader(engine, name="scheduler", owner="pod-a")
    assert try_acquire_leader(engine, name="scheduler", owner="pod-b") is True


def test_building_index_expires() -> None:
    now = datetime.now(UTC)
    row = expire_building(
        {"status": "BUILDING", "updated_at": (now - timedelta(minutes=40)).isoformat(), "retry_count": 0},
        now=now,
        timeout_seconds=30 * 60,
    )
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["failure_reason"] == "publish_timeout"
    fresh = expire_building(
        {"status": "BUILDING", "updated_at": now.isoformat(), "retry_count": 0},
        now=now,
        timeout_seconds=30 * 60,
    )
    assert fresh is None


def test_ready_fails_when_postgres_is_slow() -> None:
    payload = ready_payload(
        pg_seconds=0.5,
        valkey_ok=True,
        spaces_configured=True,
        flags_ok=True,
        strict=True,
    )
    assert payload["ok"] is False
    assert payload["checks"]["postgres"]["ok"] is False
