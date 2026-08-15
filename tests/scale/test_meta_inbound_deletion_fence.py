from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import services.scale.inbound_event_store as event_store
from services.meta_inbound_deletion_fence import (
    InboundBindingDeletionFencedError,
    InboundDeletionFenceStoreError,
    install_inbound_binding_deletion_fences,
    local_binding_deletion_is_fenced,
)
from services.meta_inbound_retention import (
    inbound_redaction_has_blockers,
    redact_inbound_events_for_bindings,
)
from services.scale.inbound_event_store import InboundEventRecord, mark_inbound_state, put_inbound_event
from tests.meta_compliance_helpers import _FakeFirestore


def _record(event_id: str, binding_id: str = "binding-target") -> InboundEventRecord:
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"instagram:account:{event_id}",
        state="accepted",
        created_at=10.0,
        updated_at=10.0,
        payload={"sender_id": "customer-private", "text": "private message"},
        settings_snapshot={"binding_id": binding_id, "tenant_id": "linas"},
        binding_snapshot={
            "binding_id": binding_id,
            "tenant_id": "linas",
            "channel": "instagram",
            "app_key": "linas_first_party",
            "auth_flow": "instagram_login",
        },
        conversation_key="linas:instagram:customer-private",
    )


def _patch_stores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db: Any,
) -> Path:
    import utils.utils

    root = tmp_path / "inbound_events"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    return root


def test_event_committed_before_fence_remains_a_deletion_blocker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    root = _patch_stores(monkeypatch, tmp_path, db)
    put_inbound_event(
        _record("ibe_before_fence"),
        enforce_binding_deletion_fence=True,
    )

    installed = install_inbound_binding_deletion_fences({"binding-target"}, now=100.0)
    stats = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=False,
        include_firestore=True,
    )

    assert installed == {"firestore_fenced": 1, "local_fenced": 1}
    assert local_binding_deletion_is_fenced("binding-target") is True
    assert (root / "ibe_before_fence.json").is_file()
    assert stats["local_active_matches"] == 1
    assert stats["firestore_active_matches"] == 1
    assert inbound_redaction_has_blockers(stats, require_firestore=True) is True


def test_fence_committed_before_event_rejects_without_local_or_firestore_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    root = _patch_stores(monkeypatch, tmp_path, db)
    install_inbound_binding_deletion_fences({"binding-target"}, now=100.0)

    with pytest.raises(InboundBindingDeletionFencedError):
        put_inbound_event(
            _record("ibe_after_fence"),
            enforce_binding_deletion_fence=True,
        )

    inbound = db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events")
    assert (root / "ibe_after_fence.json").exists() is False
    assert inbound.document("ibe_after_fence").exists is False


def test_fenced_ingress_requires_firestore_before_writing_local_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _patch_stores(monkeypatch, tmp_path, None)

    with pytest.raises(InboundDeletionFenceStoreError, match="unavailable"):
        put_inbound_event(
            _record("ibe_store_unavailable"),
            enforce_binding_deletion_fence=True,
        )

    assert (root / "ibe_store_unavailable.json").exists() is False


def test_ingress_local_write_finishes_before_concurrent_fence_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import services.meta_inbound_deletion_fence as fence_service

    db = _FakeFirestore()
    root = _patch_stores(monkeypatch, tmp_path, db)
    firestore_committed = threading.Event()
    release_ingress = threading.Event()
    fence_started = threading.Event()
    real_persist = fence_service.persist_firestore_event_unless_fenced

    def paused_persist(**kwargs: Any) -> None:
        real_persist(**kwargs)
        firestore_committed.set()
        assert release_ingress.wait(timeout=5)

    def install_fence() -> dict[str, int]:
        fence_started.set()
        return install_inbound_binding_deletion_fences({"binding-target"}, now=100.0)

    monkeypatch.setattr(fence_service, "persist_firestore_event_unless_fenced", paused_persist)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ingress = pool.submit(
            put_inbound_event,
            _record("ibe_interleaved"),
            enforce_binding_deletion_fence=True,
        )
        assert firestore_committed.wait(timeout=5)
        fencing = pool.submit(install_fence)
        assert fence_started.wait(timeout=5)
        assert fencing.done() is False
        assert (root / "ibe_interleaved.json").exists() is False
        release_ingress.set()
        ingress.result(timeout=5)
        fencing.result(timeout=5)

    stats = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=False,
        include_firestore=True,
    )
    assert (root / "ibe_interleaved.json").is_file()
    assert stats["local_active_matches"] == 1
    assert stats["firestore_active_matches"] == 1


def test_stale_state_writer_cannot_restore_payload_after_fence_and_redaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    root = _patch_stores(monkeypatch, tmp_path, db)
    stored = _record("ibe_stale_state")
    stored.state = "completed"
    put_inbound_event(stored, enforce_binding_deletion_fence=True)

    stale = _record("ibe_stale_state")
    stale.state = "processing"
    stale.payload["future_private"] = "must-never-return"
    stale_loaded = threading.Event()
    release_stale = threading.Event()
    real_get = event_store.get_inbound_event
    first_read = True

    def paused_get(_event_id: str, **_kwargs: object) -> InboundEventRecord:
        nonlocal first_read
        if first_read:
            first_read = False
            stale_loaded.set()
            assert release_stale.wait(timeout=5)
            return stale
        result = real_get(_event_id, **_kwargs)
        assert result is not None
        return result

    monkeypatch.setattr(event_store, "get_inbound_event", paused_get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        state_write = pool.submit(mark_inbound_state, stale.event_id, state="queued")
        assert stale_loaded.wait(timeout=5)
        install_inbound_binding_deletion_fences({"binding-target"}, now=100.0)
        applied = redact_inbound_events_for_bindings(
            {"binding-target"},
            apply=True,
            include_firestore=True,
            now=101.0,
        )
        assert inbound_redaction_has_blockers(applied, require_firestore=True) is False
        release_stale.set()
        with pytest.raises(event_store.InboundEventStateTransitionError, match="became terminal"):
            state_write.result(timeout=5)

    local = json.loads((root / "ibe_stale_state.json").read_text(encoding="utf-8"))
    shared_ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("inbound_events")
        .document("ibe_stale_state")
    )
    shared = shared_ref.get().to_dict()
    for document in (local, shared):
        serialized = json.dumps(document, sort_keys=True)
        assert document["payload"] == {}
        assert "private message" not in serialized
        assert "must-never-return" not in serialized
        assert "sender_id" not in serialized
        assert set(document).issubset(
            {
                "event_id",
                "kind",
                "tenant_id",
                "claim_namespace",
                "claim_key",
                "state",
                "created_at",
                "updated_at",
                "payload",
                "settings_snapshot",
                "binding_snapshot",
                "conversation_key",
                "queue_job_id",
                "attempts",
                "last_error",
                "outbound_status",
                "ai_output_persisted",
                "retention_status",
                "retention_reason",
                "retention_redacted_at",
            }
        )
