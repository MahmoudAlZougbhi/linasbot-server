"""Phase 2 durable queue + credit-safety proofs."""

from __future__ import annotations

import pytest

from services.credit_ledger_service import CreditLedgerService
from services.entitlements_service import EntitlementsStore
from services.queues.models import QueueJob


def _ledger(tmp_path, monkeypatch, tenant: str = "t1", plan: str = "pro"):
    from services import entitlements_service as es

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    store.set_plan(tenant_id=tenant, plan_id=plan, status="active", source="admin")
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    ledger.ensure_period_grant(tenant)
    return ledger, store


def test_capture_idempotent_no_double_charge(tmp_path, monkeypatch) -> None:
    ledger, _ = _ledger(tmp_path, monkeypatch)
    start = ledger.get_balance("t1")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=40,
        operation_type="creative_image",
        request_id="r1",
    )
    assert ledger.get_balance("t1") == start - 40
    first = ledger.capture(
        tenant_id="t1",
        reservation_id=rid,
        provider_cost_usd=0.04,
        model_provider="openai:img",
    )
    second = ledger.capture(
        tenant_id="t1",
        reservation_id=rid,
        provider_cost_usd=0.04,
        model_provider="openai:img",
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert ledger.get_balance("t1") == start - 40


def test_release_idempotent_after_permanent_fail(tmp_path, monkeypatch) -> None:
    ledger, _ = _ledger(tmp_path, monkeypatch)
    start = ledger.get_balance("t1")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=200,
        operation_type="creative_video",
        request_id="r2",
    )
    first = ledger.release(tenant_id="t1", reservation_id=rid)
    second = ledger.release(tenant_id="t1", reservation_id=rid)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert ledger.get_balance("t1") == start


def test_tenant_cannot_capture_other_tenant_reservation(tmp_path, monkeypatch) -> None:
    ledger, store = _ledger(tmp_path, monkeypatch, tenant="t1")
    store.set_plan(tenant_id="t2", plan_id="pro", status="active", source="admin")
    ledger.ensure_period_grant("t2")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=10,
        operation_type="creative_image",
        request_id="r3",
    )
    with pytest.raises(ValueError, match="Unknown reservation"):
        ledger.capture(
            tenant_id="t2",
            reservation_id=rid,
            provider_cost_usd=0.01,
            model_provider="x",
        )


def test_redis_enqueue_idempotent(monkeypatch) -> None:
    import fakeredis

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "false")

    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    job = QueueJob.new(
        queue="expensive",
        job_type="creative_image",
        tenant_id="t1",
        payload={"kind": "image"},
        idempotency_key="creative:image:abc",
        reservation_id="res1",
    )
    a = backend.enqueue(job)
    b = backend.enqueue(
        QueueJob.new(
            queue="expensive",
            job_type="creative_image",
            tenant_id="t1",
            payload={"kind": "image"},
            idempotency_key="creative:image:abc",
            reservation_id="res1",
        )
    )
    assert a.id == b.id
    assert backend.depth()["expensive"] == 1


def test_redis_retry_then_dlq(monkeypatch) -> None:
    import fakeredis

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    job = QueueJob.new(
        queue="high_priority",
        job_type="noop",
        tenant_id="t1",
        payload={},
        max_attempts=2,
    )
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is not None
    dead = backend.fail(claimed, error="boom", retry=True)
    assert dead is False
    claimed2 = backend.claim("high_priority", worker_id="w1", timeout=1)
    # available_at backoff may skip; force ready
    if claimed2 is None:
        j = backend.get(job.id)
        assert j is not None
        j.available_at = 0
        backend._save(j)  # noqa: SLF001
        claimed2 = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed2 is not None
    dead2 = backend.fail(claimed2, error="boom2", retry=True)
    assert dead2 is True
    assert backend.depth()["high_priority_dlq"] == 1


@pytest.mark.asyncio
async def test_creative_handler_refunds_only_via_worker_dlq_path(tmp_path, monkeypatch) -> None:
    """Permanent video misconfig raises PermanentJobError; credits stay reserved until worker refunds."""
    from services.queues.handlers import PermanentJobError, handle_creative_expensive

    ledger, _ = _ledger(tmp_path, monkeypatch)
    start = ledger.get_balance("t1")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=200,
        operation_type="creative_video",
        request_id="rv",
    )
    monkeypatch.setattr(
        "services.credit_ledger_service.credit_ledger_service",
        ledger,
    )
    job = QueueJob.new(
        queue="expensive",
        job_type="creative_video",
        tenant_id="t1",
        payload={"kind": "video", "prompt": "x", "reservation_id": rid},
        reservation_id=rid,
    )
    with pytest.raises(PermanentJobError):
        await handle_creative_expensive(job)
    # Handler must not auto-release on permanent error (worker does on DLQ).
    assert ledger.get_balance("t1") == start - 200
    ledger.release(tenant_id="t1", reservation_id=rid)
    assert ledger.get_balance("t1") == start


def test_iap_config_not_purchase_ready() -> None:
    from services.store_iap_service import external_store_checklist, iap_config_status

    status = iap_config_status()
    assert status["code_ready"] is True
    assert status["purchase_ready"] is False
    assert status["plans"]["starter"] == 24.99
    checklist = external_store_checklist()
    assert "apple" in checklist and "google" in checklist


def test_meta_capability_matrix_truthful() -> None:
    from services.integration_capabilities import list_tenant_integration_status

    rows = list_tenant_integration_status("linas")
    platforms = {r["platform"] for r in rows}
    assert "instagram" in platforms
    assert "facebook" in platforms
    assert "meta" not in platforms
    for platform in ("instagram", "facebook"):
        row = next(r for r in rows if r["platform"] == platform)
        assert row["coming_soon"] is False
        assert row["connectable"] is True
        comment = row["capabilities"]["comment_reply"]
        assert comment["supported_in_code"] is True
        assert comment["live_verified"] is False
        publish = row["capabilities"]["content_publish"]
        assert publish["live_verified"] is False
    for platform in ("tiktok", "snapchat"):
        row = next(r for r in rows if r["platform"] == platform)
        assert row["coming_soon"] is True
        assert row["connectable"] is False
        assert row["connected"] is False
