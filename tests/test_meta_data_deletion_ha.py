"""HA invariants for Meta's authenticated data-deletion workflow."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

import services.durable_event_claim as durable_claims
import services.scale.inbound_event_store as event_store
from services.meta_app_registry import APP_A_KEY
from services.meta_data_deletion import (
    MetaDeletionStoreUnavailableError,
    _DeletionBindingScope,
    _finalize_shared_request,
    _get_or_create_shared_request,
    _mark_coordinator_completed,
    _sanitize_local_and_ack,
    delete_meta_social_user_data,
    process_pending_meta_deletion_requests,
    read_deletion_status,
)
from services.meta_subject_deletion_guard import acquire_meta_oauth_subject_guard, meta_deletion_subject_hmac
from tests.meta_compliance_helpers import APP_SECRET, _FakeDocument, _FakeFirestore
from tests.test_meta_compliance_deletion import APP_A_ID, _binding, _ledger, _Registry, _write_ledger


def _shared_request(db: _FakeFirestore) -> _FakeDocument:
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    documents = [
        document for document in app.collection("meta_deletion_requests").documents.values() if document.exists
    ]
    assert len(documents) == 1
    return documents[0]


def _configure_ha_stores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db: _FakeFirestore | None,
) -> tuple[dict[str, Path], dict[str, Path]]:
    import services.meta_data_deletion as deletion_service
    import utils.utils

    roots = {"node01": tmp_path / "node01", "node02": tmp_path / "node02"}
    for root in roots.values():
        root.mkdir()
    claims_roots = {"node01": tmp_path / "node01-claims", "node02": tmp_path / "node02-claims"}
    for root in claims_roots.values():
        (root / "durable_claims").mkdir(parents=True)
    active = {"root": roots["node01"], "claims": claims_roots["node01"] / "durable_claims"}
    monkeypatch.setattr(event_store, "_store_dir", lambda: active["root"])
    monkeypatch.setattr(durable_claims, "_claims_dir", lambda: active["claims"])
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_LOCK_DIR", tmp_path / "deletion_runtime")
    monkeypatch.setenv("META_DELETION_NODE_ID", "node01")
    monkeypatch.setenv("META_DELETION_REQUIRED_NODES", "node01,node02")
    return roots, active


def _delete(registry: Any):
    return delete_meta_social_user_data(
        "123456789",
        APP_SECRET,
        app_key=APP_A_KEY,
        signing_app_id=APP_A_ID,
        auth_flow="facebook_login",
        registry=registry,
    )


def _coordinate_first_two_transaction_commits(
    monkeypatch: pytest.MonkeyPatch,
    db: _FakeFirestore,
) -> None:
    original_transaction = db.transaction
    barrier = threading.Barrier(2)
    call_lock = threading.Lock()
    call_count = 0

    def transaction() -> Any:
        nonlocal call_count
        result = original_transaction()
        with call_lock:
            call_count += 1
            coordinated = call_count <= 2
        if coordinated:
            original_commit = result.commit

            def commit() -> None:
                barrier.wait(timeout=5)
                original_commit()

            result.commit = commit
        return result

    monkeypatch.setattr(db, "transaction", transaction)


def test_two_nodes_share_code_and_status_waits_for_both_local_acks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    roots, active = _configure_ha_stores(monkeypatch, tmp_path, db)
    _write_ledger(roots["node01"], _ledger(event_id="ibe_node01", binding_id="binding-target"))
    node02_ledger = _write_ledger(
        roots["node02"],
        _ledger(event_id="ibe_node02", binding_id="binding-target"),
    )
    node02_orphan = roots["node02"] / ".ibe_crash.json.123.456.tmp"
    node02_orphan.write_text('{"payload":{"text":"private orphan"}}', encoding="utf-8")
    binding = _binding()
    binding.tenant_id = "private-tenant"
    binding.asset_id = "private-asset-id"
    binding.page_id = "445566778899"
    registry = _Registry(binding)

    first = _delete(registry)
    first_status = read_deletion_status(first.confirmation_code)
    assert first_status is not None and first_status["status"] == "pending"
    request = _shared_request(db)
    assert request.collection("node_acks").document("node01").get().exists
    assert not request.collection("node_acks").document("node02").get().exists

    active["root"] = roots["node02"]
    active["claims"] = tmp_path / "node02-claims" / "durable_claims"
    monkeypatch.setenv("META_DELETION_NODE_ID", "node02")
    reconciled = process_pending_meta_deletion_requests()

    assert reconciled == {"examined": 1, "acknowledged": 1, "completed": 1, "pending": 0, "errors": 0}
    second_status = read_deletion_status(first.confirmation_code)
    assert second_status is not None and second_status["status"] == "completed"
    assert second_status["redacted_ledger_documents"] == 2
    assert json.loads(node02_ledger.read_text(encoding="utf-8"))["payload"] == {}
    assert node02_orphan.exists() is False
    repeated = _delete(registry)
    assert repeated.confirmation_code == first.confirmation_code
    assert read_deletion_status(repeated.confirmation_code)["status"] == "completed"


def test_deletion_waiting_behind_oauth_reads_and_revokes_newly_activated_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    _configure_ha_stores(monkeypatch, tmp_path, db)
    registry = _Registry()
    subject_key = meta_deletion_subject_hmac(
        app_key=APP_A_KEY,
        app_id=APP_A_ID,
        auth_flow="facebook_login",
        meta_user_id="123456789",
        app_secret=APP_SECRET,
    )
    oauth_guard = acquire_meta_oauth_subject_guard(subject_key)

    with ThreadPoolExecutor(max_workers=1) as pool:
        deletion = pool.submit(_delete, registry)
        threading.Event().wait(0.08)
        assert deletion.done() is False
        activated = _binding()
        registry.bindings.append(activated)
        oauth_guard.assert_oauth_snapshot_unchanged()
        oauth_guard.release()
        result = deletion.result(timeout=5)

    assert result.revoked_bindings == 1
    assert activated.status == "disconnected"
    assert activated.generation == 2
    assert read_deletion_status(result.confirmation_code)["status"] == "pending"


def test_two_coordinators_contending_on_subject_index_create_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _coordinate_first_two_transaction_commits(monkeypatch, db)
    kwargs = {
        "db": db,
        "subject_key": "a" * 64,
        "app_key": APP_A_KEY,
        "app_id": APP_A_ID,
        "auth_flow": "facebook_login",
        "bindings": (_DeletionBindingScope("binding-target", 1),),
        "required_nodes": ("node01", "node02"),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(_get_or_create_shared_request, **kwargs) for _ in range(2)]
        requests = [future.result(timeout=10) for future in results]

    assert requests[0].confirmation_code == requests[1].confirmation_code
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    assert len([doc for doc in app.collection("meta_deletion_subject_index").documents.values() if doc.exists]) == 1
    assert len([doc for doc in app.collection("meta_deletion_requests").documents.values() if doc.exists]) == 1


def test_coordinator_completion_racing_scope_update_cannot_regress_reopened_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    subject_key = "b" * 64
    request = _get_or_create_shared_request(
        db=db,
        subject_key=subject_key,
        app_key=APP_A_KEY,
        app_id=APP_A_ID,
        auth_flow="facebook_login",
        bindings=(_DeletionBindingScope("binding-target", 1),),
        required_nodes=("node01", "node02"),
    )
    _coordinate_first_two_transaction_commits(monkeypatch, db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        completion = pool.submit(
            _mark_coordinator_completed,
            db,
            request,
            revoked_bindings=1,
            shared_redacted_documents=0,
            current_bindings=(_DeletionBindingScope("binding-target", 2),),
        )
        reopen = pool.submit(
            _get_or_create_shared_request,
            db=db,
            subject_key=subject_key,
            app_key=APP_A_KEY,
            app_id=APP_A_ID,
            auth_flow="facebook_login",
            bindings=(_DeletionBindingScope("binding-target", 3),),
            required_nodes=("node01", "node02"),
        )
        completion.result(timeout=10)
        reopened = reopen.result(timeout=10)

    assert reopened.generation == 2
    persisted = _shared_request(db)
    assert persisted.data["generation"] == 2
    assert persisted.data["state"] == "pending"
    assert persisted.data["coordinator_state"] == "pending"
    assert persisted.data["current_bindings"] == [{"binding_id": "binding-target", "expected_generation": 3}]


def test_node_ack_racing_request_reopen_is_never_valid_for_new_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    _configure_ha_stores(monkeypatch, tmp_path, db)
    subject_key = "c" * 64
    request = _get_or_create_shared_request(
        db=db,
        subject_key=subject_key,
        app_key=APP_A_KEY,
        app_id=APP_A_ID,
        auth_flow="facebook_login",
        bindings=(_DeletionBindingScope("binding-target", 1),),
        required_nodes=("node01", "node02"),
    )
    coordinated = _mark_coordinator_completed(
        db,
        request,
        revoked_bindings=1,
        shared_redacted_documents=0,
        current_bindings=(_DeletionBindingScope("binding-target", 1),),
    )
    _coordinate_first_two_transaction_commits(monkeypatch, db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        acknowledgement = pool.submit(_sanitize_local_and_ack, db, coordinated)
        reopen = pool.submit(
            _get_or_create_shared_request,
            db=db,
            subject_key=subject_key,
            app_key=APP_A_KEY,
            app_id=APP_A_ID,
            auth_flow="facebook_login",
            bindings=(_DeletionBindingScope("binding-target", 2),),
            required_nodes=("node01", "node02"),
        )
        try:
            acknowledgement.result(timeout=10)
        except MetaDeletionStoreUnavailableError:
            pass
        reopened = reopen.result(timeout=10)

    assert reopened.generation == 2
    persisted = _shared_request(db)
    ack = persisted.collection("node_acks").document("node01")
    assert not ack.exists or ack.data["request_generation"] == 1
    assert persisted.data["generation"] == 2
    assert persisted.data["coordinator_state"] == "pending"
    assert _finalize_shared_request(db, reopened.confirmation_code).state == "pending"


def test_finalize_racing_scope_generation_update_reopens_without_terminal_regression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    _configure_ha_stores(monkeypatch, tmp_path, db)
    registry = _Registry(_binding())
    result = _delete(registry)
    request = _shared_request(db)
    generation = request.data["generation"]
    request.collection("node_acks").document("node02").set(
        {
            "schema_version": 1,
            "node_id": "node02",
            "status": "completed",
            "request_generation": generation,
            "acknowledged_at": 1_800_000_000,
            "local_redacted_documents": 0,
            "local_blockers": 0,
            "local_remaining_changes": 0,
        }
    )
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    subject_key = next(iter(app.collection("meta_deletion_subject_index").documents))
    _coordinate_first_two_transaction_commits(monkeypatch, db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        finalize = pool.submit(_finalize_shared_request, db, result.confirmation_code)
        reopen = pool.submit(
            _get_or_create_shared_request,
            db=db,
            subject_key=subject_key,
            app_key=APP_A_KEY,
            app_id=APP_A_ID,
            auth_flow="facebook_login",
            bindings=(_DeletionBindingScope("binding-target", 3),),
            required_nodes=("node01", "node02"),
        )
        finalize.result(timeout=10)
        reopened = reopen.result(timeout=10)

    assert reopened.generation == 2
    assert reopened.state == "pending"
    assert reopened.coordinator_state == "pending"
    persisted = _shared_request(db)
    assert persisted.data["generation"] == 2
    assert persisted.data["state"] == "pending"
    assert persisted.data["current_bindings"] == [{"binding_id": "binding-target", "expected_generation": 3}]
    assert _finalize_shared_request(db, result.confirmation_code).state == "pending"


def test_stale_and_unknown_node_acks_cannot_finalize_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    roots, active = _configure_ha_stores(monkeypatch, tmp_path, db)
    registry = _Registry(_binding())
    result = _delete(registry)
    request = _shared_request(db)
    generation = int(request.data["generation"])
    ack_payload = {
        "schema_version": 1,
        "status": "completed",
        "request_generation": generation,
        "acknowledged_at": 1_800_000_000,
        "local_redacted_documents": 0,
        "local_blockers": 0,
        "local_remaining_changes": 0,
    }
    request.collection("node_acks").document("unknown-node").set(ack_payload | {"node_id": "unknown-node"})
    request.collection("node_acks").document("node02").set(
        ack_payload | {"node_id": "node02", "request_generation": generation - 1}
    )

    pending = _finalize_shared_request(db, result.confirmation_code)
    assert pending.state == "pending"

    active["root"] = roots["node02"]
    monkeypatch.setenv("META_DELETION_NODE_ID", "node02")
    process_pending_meta_deletion_requests()
    assert read_deletion_status(result.confirmation_code)["status"] == "completed"


def test_completed_request_reopens_when_same_binding_generation_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    roots, active = _configure_ha_stores(monkeypatch, tmp_path, db)
    binding = _binding()
    registry = _Registry(binding)

    first = _delete(registry)
    active["root"] = roots["node02"]
    monkeypatch.setenv("META_DELETION_NODE_ID", "node02")
    process_pending_meta_deletion_requests()
    request = _shared_request(db)
    assert request.data["state"] == "completed"
    assert request.data["generation"] == 1
    assert request.data["current_bindings"] == [{"binding_id": binding.binding_id, "expected_generation": 2}]

    # Model a same-subject credential write that reused the binding identity.
    # The generation snapshot, not only the historical ID union, must reopen it.
    binding.status = "active"
    binding.generation += 1
    active["root"] = roots["node01"]
    monkeypatch.setenv("META_DELETION_NODE_ID", "node01")
    repeated = _delete(registry)

    assert repeated.confirmation_code == first.confirmation_code
    request = _shared_request(db)
    assert request.data["state"] == "pending"
    assert request.data["generation"] == 2
    assert request.data["current_bindings"] == [{"binding_id": binding.binding_id, "expected_generation": 4}]
    assert request.collection("node_acks").document("node01").data["request_generation"] == 2
    assert request.collection("node_acks").document("node02").data["request_generation"] == 1

    active["root"] = roots["node02"]
    monkeypatch.setenv("META_DELETION_NODE_ID", "node02")
    process_pending_meta_deletion_requests()
    assert read_deletion_status(first.confirmation_code)["status"] == "completed"


def test_failed_registry_conflict_reopens_on_new_binding_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _ConflictOnceRegistry(_Registry):
        fail_once = True

        def revoke_authorization_exact(self, **kwargs: Any) -> list[Any]:
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("private provider conflict detail")
            return super().revoke_authorization_exact(**kwargs)

    db = _FakeFirestore()
    _configure_ha_stores(monkeypatch, tmp_path, db)
    binding = _binding()
    registry = _ConflictOnceRegistry(binding)

    with pytest.raises(RuntimeError, match="private provider conflict"):
        _delete(registry)
    failed = _shared_request(db)
    code = failed.data["confirmation_code"]
    assert failed.data["state"] == "failed"
    assert failed.data["generation"] == 1
    assert failed.data["safe_error"] == "registry_conflict"
    assert "private provider conflict" not in json.dumps(failed.data)

    binding.generation += 1
    retried = _delete(registry)
    assert retried.confirmation_code == code
    reopened = _shared_request(db)
    assert reopened.data["state"] == "pending"
    assert reopened.data["generation"] == 2
    assert reopened.data["safe_error"] == "none"
    assert reopened.data["current_bindings"] == [{"binding_id": binding.binding_id, "expected_generation": 3}]


def test_shared_documents_never_serialize_raw_subject_tenant_token_asset_or_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    _roots, _active = _configure_ha_stores(monkeypatch, tmp_path, db)
    binding = _binding()
    binding.tenant_id = "private-tenant"
    binding.asset_id = "private-asset-id"
    binding.page_id = "445566778899"
    registry = _Registry(binding)
    _delete(registry)
    request = _shared_request(db)
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    subject_index = app.collection("meta_deletion_subject_index")
    payloads = [request.data]
    payloads.extend(document.data for document in subject_index.documents.values() if document.exists)
    payloads.extend(document.data for document in request.collection("node_acks").documents.values() if document.exists)
    serialized = json.dumps(payloads, sort_keys=True)
    for sensitive in (
        "123456789",
        "private-tenant",
        "must-disappear",
        "private-asset-id",
        "private message",
        "provider-private-detail",
        APP_SECRET,
    ):
        assert sensitive not in serialized
    assert all("123456789" not in document_id for document_id in subject_index.documents)
    assert "tenant_id" not in serialized


def test_shared_status_and_callback_fail_closed_without_firestore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ha_stores(monkeypatch, tmp_path, None)
    with pytest.raises(MetaDeletionStoreUnavailableError):
        read_deletion_status("a" * 32)
    with pytest.raises(MetaDeletionStoreUnavailableError):
        _delete(_Registry())
