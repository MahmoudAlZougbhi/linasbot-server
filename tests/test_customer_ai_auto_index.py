"""Automatic per-tenant Customer Brain indexing: publish, edit, delete, retry, isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_ai.providers.voyage_client import VoyageVectors
from services.customer_ai.search.index_lifecycle import get_lifecycle, reset_lifecycle_for_tests
from services.customer_ai.search.store import reset_memory_store, tenant_pointer_ready
from services.membership.processing_budgets import reset_processing_budgets_for_tests


@pytest.fixture()
def tenant_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from db.session import WhatsAppDatabaseUnavailable
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))

    def _no_db(*_a: object, **_k: object) -> None:
        raise WhatsAppDatabaseUnavailable("test")

    monkeypatch.setattr("db.session.whatsapp_session", _no_db)
    monkeypatch.setattr("services.queues.config.is_production_env", lambda: False)
    reset_lifecycle_for_tests()
    reset_memory_store()
    reset_processing_budgets_for_tests()
    return tmp_path


@pytest.fixture()
def mock_voyage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key-not-used")

    async def _texts(space: object, texts: list[str]) -> VoyageVectors:
        sid = getattr(space, "space_id", "entity")
        return VoyageVectors(space_id=str(sid), vectors=[[0.2, 0.1, 0.0, 0.0] for _ in texts])

    async def _groups(space: object, groups: list[list[str]]) -> list[VoyageVectors]:
        sid = getattr(space, "space_id", "knowledge")
        return [VoyageVectors(space_id=str(sid), vectors=[[0.3, 0.1, 0.0, 0.0] for _ in group]) for group in groups]

    monkeypatch.setattr("services.customer_ai.search.index_job.voyage_configured", lambda: True)
    monkeypatch.setattr("services.customer_ai.search.contextual_index.voyage_configured", lambda: True)
    monkeypatch.setattr("services.customer_ai.search.index_job.embed_texts", _texts)
    monkeypatch.setattr("services.customer_ai.search.contextual_index.embed_contextual_groups", _groups)


@pytest.mark.asyncio
async def test_new_tenant_publish_indexes_without_admin(tenant_fs: Path, mock_voyage: None) -> None:
    from services.customer_ai.evals.auto_index_e2e import run_new_tenant_auto_index_e2e
    from services.queues.handlers import get_handler

    assert get_handler("customer_ai_index") is not None
    result = await run_new_tenant_auto_index_e2e()
    assert result["ok"] is True
    assert result["first_active"] is True
    assert result["edit_new_active"] is True
    assert result["faq_removed"] is True
    assert result["manual_index_required"] is False
    life = result["lifecycle"]
    assert life["status"] == "ACTIVE"
    assert life["rollback_version"]
    assert life["active_version"] != life["rollback_version"]


@pytest.mark.asyncio
async def test_durable_queue_marks_building_without_inline(monkeypatch: pytest.MonkeyPatch, tenant_fs: Path) -> None:
    from services.customer_ai.search.index_schedule import schedule_tenant_index

    captured: dict[str, object] = {}

    def _enqueue(tenant_id: str, *, revision: str = "", reason: str = "publish") -> dict[str, object]:
        captured["tenant_id"] = tenant_id
        captured["revision"] = revision
        captured["reason"] = reason
        return {
            "ready": False,
            "indexing": True,
            "queued": True,
            "job_id": "job-1",
            "version": revision,
            "health": "BUILDING",
            "manual_index_required": False,
        }

    monkeypatch.setattr("services.customer_ai.search.index_schedule.uses_index_worker", lambda: True)
    monkeypatch.setattr("services.customer_ai.search.index_schedule.enqueue_tenant_index", _enqueue)
    monkeypatch.setattr(
        "services.customer_ai.search.index_schedule.published_revision",
        lambda _tid: "rev-1",
    )
    out = await schedule_tenant_index("shop-a", revision="rev-1", reason="publish")
    assert out["queued"] is True
    assert out["health"] == "BUILDING"
    assert captured["tenant_id"] == "shop-a"
    assert result_not_inlined(out)


def result_not_inlined(out: dict[str, object]) -> bool:
    return "entity" not in out


@pytest.mark.asyncio
async def test_embed_failure_keeps_old_active_and_retries(
    tenant_fs: Path, mock_voyage: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.cm.publish import publish_draft
    from services.customer_ai.evals.auto_index_e2e import seed_minimal_setup
    from services.customer_ai.search.index_job import index_published_tenant

    seed_minimal_setup("retry-shop", price="80 USD", faq=True)
    first = await publish_draft(tenant_id="retry-shop", published_by="tester")
    assert first.brain_index_status and first.brain_index_status.get("ready") is True
    assert tenant_pointer_ready(None, "retry-shop") is True
    old = str(get_lifecycle("retry-shop").get("active_version") or "")

    async def _boom(*_a: object, **_k: object) -> list[list[float]]:
        raise RuntimeError("voyage_down")

    async def _ok_embed(rows: list[object]) -> list[list[float]]:
        return [[0.2, 0.1, 0.0, 0.0] for _ in rows]

    monkeypatch.setattr("services.customer_ai.search.index_job.embed_document_rows", _boom)
    failed = await index_published_tenant("retry-shop", revision="will-fail")
    assert failed["ready"] is False
    assert get_lifecycle("retry-shop")["status"] == "FAILED"
    assert tenant_pointer_ready(None, "retry-shop") is True
    assert get_lifecycle("retry-shop")["active_version"] == old or old == first.content_version_id

    monkeypatch.setattr(
        "services.customer_ai.search.index_job.embed_document_rows",
        _ok_embed,
    )
    again = await index_published_tenant("retry-shop", revision=first.content_version_id)
    assert again["ready"] is True
    assert get_lifecycle("retry-shop")["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_tenant_isolation_and_product_change_enqueues(tenant_fs: Path, mock_voyage: None) -> None:
    from services.cm.publish import publish_draft
    from services.customer_ai.evals.auto_index_e2e import seed_minimal_setup
    from services.customer_ai.providers.spaces import ENTITY_DOCUMENT
    from services.customer_ai.search.index_schedule import run_tenant_index_job
    from services.customer_ai.search.invalidate import notify_product_change
    from services.customer_ai.search.store import query_similar

    seed_minimal_setup("iso-a", price="80 USD", faq=True)
    seed_minimal_setup("iso-b", price="80 USD", faq=True)
    await publish_draft(tenant_id="iso-a", published_by="tester")
    await publish_draft(tenant_id="iso-b", published_by="tester")
    hits_a = query_similar(
        None,
        tenant_id="iso-a",
        space_id=ENTITY_DOCUMENT.space_id,
        vector=[0.2, 0.1, 0.0, 0.0],
        limit=20,
    )
    assert hits_a.items
    assert all(hit.tenant_id == "iso-a" for hit in hits_a.items)
    hits_other = query_similar(
        None,
        tenant_id="missing-tenant",
        space_id=ENTITY_DOCUMENT.space_id,
        vector=[0.2, 0.1, 0.0, 0.0],
        limit=20,
    )
    assert all(hit.tenant_id != "iso-a" for hit in hits_other.items)

    notify_product_change(None, "iso-a")
    life = get_lifecycle("iso-a")
    assert life["status"] in {"STALE", "BUILDING", "ACTIVE"}
    rebuilt = await run_tenant_index_job("iso-a", reason="products_changed")
    assert rebuilt.get("ready") is True
    assert get_lifecycle("iso-a")["status"] == "ACTIVE"


def test_real_linas_resolver_refuses_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.evals.linas_real_index import resolve_real_tenant_id

    monkeypatch.setenv("LINAS_REAL_TENANT_ID", "linas-lab")
    with pytest.raises(RuntimeError, match="refusing_lab"):
        resolve_real_tenant_id()
    monkeypatch.setenv("LINAS_REAL_TENANT_ID", "linas")
    assert resolve_real_tenant_id() == "linas"


def test_owner_status_has_no_secret_keys() -> None:
    from services.customer_ai.search.index_lifecycle import owner_status, upsert_lifecycle

    upsert_lifecycle("vis-shop", status="ACTIVE", failure_reason="provider_error", embedding_model="voyage-4-large")
    row = owner_status("vis-shop")
    blob = str(row)
    assert "VOYAGE" not in blob
    assert "sk-" not in blob
    assert row["manual_index_required"] is False
    assert "status" in row
    assert "retry_count" in row


def test_backfill_is_bounded(tenant_fs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.search import index_backfill

    monkeypatch.setattr(index_backfill, "published_tenant_ids", lambda: ["t1", "t2", "t3", "t4"])
    monkeypatch.setattr(index_backfill, "tenant_needs_index", lambda _tid: True)

    async def _sched(tid: str, **_k: object) -> dict[str, object]:
        return {"queued": True, "health": "BUILDING", "reason": "backfill"}

    monkeypatch.setattr("services.customer_ai.search.index_schedule.schedule_tenant_index", _sched)

    async def _run() -> None:
        out = await index_backfill.enqueue_stale_or_missing(limit=2, skip={"t1"})
        assert out["scheduled_count"] == 2
        assert [row["tenant_id"] for row in out["scheduled"]] == ["t2", "t3"]

    __import__("asyncio").run(_run())
