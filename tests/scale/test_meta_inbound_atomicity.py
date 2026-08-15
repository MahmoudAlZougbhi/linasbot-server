from __future__ import annotations

import copy
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import services.durable_event_claim as claims
import services.scale.inbound_event_reconcile as reconcile
import services.scale.inbound_event_store as event_store
from services.scale.inbound_event_store import InboundEventRecord
from tests.meta_compliance_helpers import _FakeFirestore


@pytest.fixture()
def shared_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_FakeFirestore, Path]:
    import utils.utils

    db = _FakeFirestore()
    root = tmp_path / "inbound"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setenv("ENVIRONMENT", "production")
    return db, root


def _record(*, event_id: str, state: str = "accepted") -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"facebook:{event_id}",
        state=state,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        payload={"channel": "facebook", "text": "customer content"},
        settings_snapshot={"binding_id": "binding-ha-1"},
        binding_snapshot={"binding_id": "binding-ha-1"},
    )


def test_provider_redelivery_returns_existing_row_without_reopening_terminal_state(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    event_id = "ibe_" + "1" * 40
    accepted, created = event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    assert created is True
    accepted.state = "completed"
    completed = event_store.put_inbound_event(accepted)
    assert completed.state == "completed"

    redelivery, created = event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    assert created is False
    assert redelivery.state == "completed"
    assert redelivery.revision == completed.revision


def test_stale_peer_cannot_regress_completed_shared_event(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    event_id = "ibe_" + "2" * 40
    original, _ = event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    stale_peer = copy.deepcopy(original)

    original.state = "completed"
    completed = event_store.put_inbound_event(original)
    stale_peer.state = "failed"
    stale_peer.last_error = "simulated_stale_peer"
    result = event_store.put_inbound_event(stale_peer)

    assert completed.state == "completed"
    assert result.state == "completed"
    assert event_store.get_inbound_event(event_id).state == "completed"  # type: ignore[union-attr]


def test_terminal_transition_retries_revision_conflict_before_claim_may_complete(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _ = shared_ledger
    event_id = "ibe_" + "9" * 40
    original, _ = event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    original.state = "processing"
    processing = event_store.put_inbound_event(original)
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    real_put = event_store.put_inbound_event
    injected = False

    def race_once(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal injected
        if record.state == "completed" and not injected:
            injected = True
            competing = copy.deepcopy(reference.data)
            competing["state"] = "queued"
            competing["revision"] = int(competing.get("revision") or 0) + 1
            reference.set(competing)
        return real_put(record, **kwargs)

    monkeypatch.setattr(event_store, "put_inbound_event", race_once)
    completed = event_store.mark_inbound_state(
        event_id,
        state="completed",
        outbound_status="sent",
        ai_output_persisted=True,
    )

    assert injected is True
    assert completed is not None and completed.state == "completed"
    assert reference.data["state"] == "completed"
    assert int(reference.data["revision"]) >= processing.revision + 2


def test_missing_authoritative_event_cannot_be_followed_by_claim_completion(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    with pytest.raises(event_store.InboundEventStateTransitionError, match="unavailable"):
        event_store.mark_inbound_state("ibe_" + "0" * 40, state="completed")


def test_stale_local_cache_cannot_resurrect_missing_shared_authority(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, root = shared_ledger
    event_id = "ibe_" + "a" * 40
    event_store.create_inbound_event(
        _record(event_id=event_id, state="processing"),
        enforce_binding_deletion_fence=True,
    )
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    reference.delete()
    assert (root / f"{event_id}.json").is_file()

    writes = 0
    real_put = event_store.put_inbound_event

    def count_put(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal writes
        writes += 1
        return real_put(record, **kwargs)

    monkeypatch.setattr(event_store, "put_inbound_event", count_put)
    with pytest.raises(event_store.InboundEventStateTransitionError, match="unavailable"):
        event_store.mark_inbound_state(event_id, state="completed")

    assert writes == 0
    assert reference.exists is False


def test_shared_row_deleted_between_read_and_transition_is_not_recreated(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _ = shared_ledger
    event_id = "ibe_" + "b" * 40
    event_store.create_inbound_event(
        _record(event_id=event_id, state="processing"),
        enforce_binding_deletion_fence=True,
    )
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    real_put = event_store.put_inbound_event
    deleted = False

    def delete_before_transaction(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal deleted
        if not deleted:
            deleted = True
            reference.delete()
        return real_put(record, **kwargs)

    monkeypatch.setattr(event_store, "put_inbound_event", delete_before_transaction)
    with pytest.raises(event_store.InboundEventStateTransitionError, match="disappeared"):
        event_store.mark_inbound_state(event_id, state="completed")

    assert deleted is True
    assert reference.exists is False
    assert event_store._file_get(event_id).state == "processing"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_queue_completes_claim_only_after_authoritative_terminal_transition(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.queues.meta_inbound_handler import handle_meta_inbound_process
    from services.queues.models import QueueJob

    db, _ = shared_ledger
    event_id = "ibe_" + "8" * 40
    event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    real_put = event_store.put_inbound_event
    injected = False
    completed_states: list[str] = []
    claim_handle = SimpleNamespace(owner_token="owner-" + "x" * 40, generation=1)

    def race_once(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal injected
        if record.state == "completed" and not injected:
            injected = True
            competing = copy.deepcopy(reference.data)
            competing["state"] = "queued"
            competing["revision"] = int(competing.get("revision") or 0) + 1
            reference.set(competing)
        return real_put(record, **kwargs)

    async def acquire(*_args: Any, **_kwargs: Any) -> Any:
        return claim_handle

    async def run_claim(*_args: Any, operation: Any, **_kwargs: Any) -> Any:
        return await operation()

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"delivery": "blocked_quota", "retryable": False, "terminal": True}

    async def complete(*_args: Any, **_kwargs: Any) -> None:
        completed_states.append(str(reference.data.get("state")))

    monkeypatch.setattr(event_store, "put_inbound_event", race_once)
    monkeypatch.setattr("services.durable_event_claim.try_claim_event_handle", acquire)
    monkeypatch.setattr("services.durable_event_claim.run_under_event_claim", run_claim)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr(
        "services.queues.meta_inbound_handler._settings_from_snapshot",
        lambda *_args: SimpleNamespace(binding_id="binding-ha-1"),
    )

    result = await handle_meta_inbound_process(
        QueueJob.new(
            queue="high_priority",
            job_type="meta_inbound_process",
            tenant_id="linas",
            payload={"event_id": event_id, "kind": "meta_dm"},
        )
    )

    assert result["ok"] is True
    assert injected is True
    assert completed_states == ["completed"]


def test_inline_completion_wrapper_proves_authoritative_terminal_transition(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.scale.meta_ingress import mark_dm_completed

    db, _ = shared_ledger
    event_id = "ibe_" + "7" * 40
    event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    real_put = event_store.put_inbound_event
    injected = False

    def race_once(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal injected
        if record.state == "completed" and not injected:
            injected = True
            competing = copy.deepcopy(reference.data)
            competing["state"] = "queued"
            competing["revision"] = int(competing.get("revision") or 0) + 1
            reference.set(competing)
        return real_put(record, **kwargs)

    monkeypatch.setattr(event_store, "put_inbound_event", race_once)
    mark_dm_completed(event_id, outbound_status="sent", ai_output_persisted=True)

    assert injected is True
    assert reference.data["state"] == "completed"


def test_watchdog_completes_claim_only_after_authoritative_dead_letter(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _ = shared_ledger
    event_id = "ibe_" + "6" * 40
    record = _record(event_id=event_id, state="failed")
    record.attempts = 8
    event_store.create_inbound_event(
        record,
        enforce_binding_deletion_fence=True,
    )
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events").document(event_id)
    )
    real_put = event_store.put_inbound_event
    real_complete = claims.complete_event_claim
    injected = False
    completed_states: list[str] = []

    def race_once(record: InboundEventRecord, **kwargs: object) -> InboundEventRecord:
        nonlocal injected
        if record.state == "dead_letter" and not injected:
            injected = True
            competing = copy.deepcopy(reference.data)
            competing["state"] = "queued"
            competing["revision"] = int(competing.get("revision") or 0) + 1
            reference.set(competing)
        return real_put(record, **kwargs)

    async def complete(*args: Any, **kwargs: Any) -> Any:
        completed_states.append(str(reference.data.get("state")))
        return await real_complete(*args, **kwargs)

    monkeypatch.setattr(event_store, "put_inbound_event", race_once)
    monkeypatch.setattr(claims, "complete_event_claim", complete)
    monkeypatch.setattr(
        reconcile,
        "list_active_inbound_events",
        lambda **_kwargs: [event_store.get_inbound_event(event_id)],
    )
    monkeypatch.setattr(reconcile, "accountability_stats", lambda: {"unexplained_missing_events": 0})

    result = reconcile.reconcile_stuck_inbound_events(older_than_seconds=0)

    assert any(item.get("event_id") == event_id and item.get("action") == "dead_letter" for item in result["actions"])
    assert injected is True
    assert completed_states == ["dead_letter"]


def test_shared_primary_is_read_before_stale_local_cache(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    event_id = "ibe_" + "3" * 40
    primary, _ = event_store.create_inbound_event(
        _record(event_id=event_id),
        enforce_binding_deletion_fence=True,
    )
    primary.state = "completed"
    primary = event_store.put_inbound_event(primary)

    stale = copy.deepcopy(primary)
    stale.state = "processing"
    stale.revision = max(0, primary.revision - 1)
    event_store._atomic_json_put(event_store._path_for(event_id), stale.to_dict())

    loaded = event_store.get_inbound_event(event_id)
    assert loaded is not None and loaded.state == "completed"
    assert event_store._file_get(event_id).state == "completed"  # type: ignore[union-attr]


def test_watchdog_skips_local_orphan_and_reconciles_later_shared_event(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan = _record(event_id="ibe_" + "c" * 40, state="failed")
    orphan.updated_at = 1.0
    event_store._file_put(orphan)
    terminal_local = _record(event_id="ibe_" + "e" * 40, state="completed")
    event_store._file_put(terminal_local)

    valid = _record(event_id="ibe_" + "d" * 40, state="failed")
    valid.attempts = 8
    valid, _ = event_store.create_inbound_event(
        valid,
        enforce_binding_deletion_fence=True,
    )
    claimed: list[str] = []
    completed: list[str] = []
    handle = SimpleNamespace(owner_token="owner-" + "z" * 40, generation=1)
    checked_authority: list[str] = []
    real_collection = event_store._firestore_inbound_collection(shared_ledger[0])

    class TrackingCollection:
        def document(self, event_id: str) -> Any:
            checked_authority.append(event_id)
            return real_collection.document(event_id)

    async def acquire(_namespace: str, key: str, **_kwargs: Any) -> Any:
        claimed.append(key)
        return handle

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    monkeypatch.setattr(
        event_store,
        "_shared_active_records",
        lambda _collection, *, local_event_ids: {valid.event_id: valid},
    )
    monkeypatch.setattr(event_store, "_firestore_inbound_collection", lambda _db: TrackingCollection())
    monkeypatch.setattr(claims, "try_claim_event_handle", acquire)
    monkeypatch.setattr(claims, "complete_event_claim", complete)

    result = reconcile.reconcile_stuck_inbound_events(older_than_seconds=0.0)

    assert result["examined"] == 1
    assert result["actions"] == [{"event_id": valid.event_id, "action": "dead_letter"}]
    assert result["unexplained_missing_events"] == 1
    assert claimed == [valid.claim_key]
    assert completed == [valid.claim_key]
    assert checked_authority == [orphan.event_id]
    assert event_store._file_get(orphan.event_id).state == "failed"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_scheduled_watchdog_reports_orphan_count_without_reconcile_candidates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import modules.inbound_event_reconcile_job as job

    monkeypatch.setattr(job, "try_acquire_job_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(job, "release_job_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        reconcile,
        "reconcile_stuck_inbound_events",
        lambda **_kwargs: {"examined": 0, "actions": [], "unexplained_missing_events": 1},
    )

    await job.run_inbound_event_reconcile_job()

    output = capsys.readouterr().out
    assert "examined=0" in output
    assert "unexplained_missing=1" in output


@pytest.mark.asyncio
async def test_expired_firestore_claim_can_be_recovered_after_claim_owner_crash(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    db, _ = shared_ledger
    claim_collection = "meta_social_dm_global_claims"
    namespace = "meta_social_dm_global"
    key = "facebook:provider-mid-crash"

    assert await claims.try_claim_event(
        namespace,
        key,
        ttl_seconds=0.01,
        firestore_collection=claim_collection,
    )
    document_id = claims._firestore_claim_document_id(namespace, key)
    reference = (
        db.collection("artifacts").document("linas-ai-bot-backend").collection(claim_collection).document(document_id)
    )
    reference.update({"expires_at_epoch": time.time() - 1})

    assert await claims.try_claim_event(
        namespace,
        key,
        ttl_seconds=300,
        firestore_collection=claim_collection,
    )
    assert reference.data["status"] == "claimed"
    assert reference.data["expires_at_epoch"] > time.time()


@pytest.mark.asyncio
async def test_released_firestore_claim_can_be_reacquired_by_new_generation(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    db, _ = shared_ledger
    namespace = "meta_social_dm_global"
    collection = "meta_social_dm_global_claims"
    key = "facebook:provider-mid-retry"

    first = await claims.try_claim_event_handle(
        namespace,
        key,
        firestore_collection=collection,
    )
    assert first is not None
    await claims.release_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )

    second = await claims.try_claim_event_handle(
        namespace,
        key,
        firestore_collection=collection,
    )
    assert second is not None
    assert second.generation == first.generation + 1

    # A delayed completion/release from the prior owner cannot mutate the new
    # worker's generation.
    await claims.complete_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )
    await claims.release_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )
    document_id = claims._firestore_claim_document_id(namespace, key)
    reference = db.collection("artifacts").document("linas-ai-bot-backend").collection(collection).document(document_id)
    assert reference.data["status"] == "claimed"
    assert reference.data["generation"] == second.generation


@pytest.mark.asyncio
async def test_watchdog_never_bumps_or_dead_letters_event_with_live_owner(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = "ibe_" + "4" * 40
    rec = _record(event_id=event_id, state="processing")
    rec.attempts = 7
    namespace = "meta_social_dm_global"
    collection = "meta_social_dm_global_claims"
    live = await claims.try_claim_event_handle(
        namespace,
        rec.claim_key,
        ttl_seconds=300,
        firestore_collection=collection,
    )
    assert live is not None
    monkeypatch.setattr(reconcile, "list_active_inbound_events", lambda **_kwargs: [rec])
    monkeypatch.setattr(reconcile, "accountability_stats", lambda: {"unexplained_missing_events": 0})
    transitions: list[dict[str, object]] = []
    monkeypatch.setattr(
        reconcile,
        "mark_inbound_state",
        lambda *_args, **kwargs: transitions.append(kwargs),
    )

    for _ in range(12):
        result = reconcile.reconcile_stuck_inbound_events(older_than_seconds=0)
        assert result["actions"] == [{"event_id": event_id, "action": "live_claim_skipped"}]

    assert rec.attempts == 7
    assert transitions == []


@pytest.mark.asyncio
async def test_binding_fence_prevents_new_ai_or_global_claim(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    db, _ = shared_ledger
    binding_id = "binding-deletion-fenced"
    from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    firestore_binding_deletion_fence_ref(db, binding_id).set({"status": "fenced"})
    handle = await claims.try_claim_event_handle(
        "ai_turn_claims",
        "private-key-basis",
        firestore_collection="ai_turn_claims",
        meta_binding_id=binding_id,
        firestore_claim_metadata={"binding_id_sha256": claims.meta_claim_binding_digest(binding_id)},
    )

    assert handle is None
