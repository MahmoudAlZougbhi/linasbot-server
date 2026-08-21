"""Google-SDK-like Firestore regressions for Meta data-deletion transactions."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_app_registry import APP_A_KEY
from services.meta_data_deletion import (
    _DeletionBindingScope,
    _finalize_shared_request,
    _get_or_create_shared_request,
    _mark_coordinator_completed,
    _sanitize_local_and_ack,
)
from tests.meta_compliance_helpers import (
    _GoogleLikeFirestore,
    _install_google_transactional_fake,
)
from tests.test_meta_compliance_deletion import APP_A_ID
from tests.test_meta_data_deletion_ha import _configure_ha_stores, _shared_request

_SUBJECT_KEY = "a" * 64
_REQUIRED_NODES = ("node01", "node02")


def _create_kwargs(db: _GoogleLikeFirestore) -> dict[str, object]:
    return {
        "db": db,
        "subject_key": _SUBJECT_KEY,
        "app_key": APP_A_KEY,
        "app_id": APP_A_ID,
        "auth_flow": "facebook_login",
        "required_nodes": _REQUIRED_NODES,
    }


def test_google_transactional_deletion_lifecycle_create_merge_update_ack_finalize(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _GoogleLikeFirestore()
    _install_google_transactional_fake(monkeypatch)
    _configure_ha_stores(monkeypatch, tmp_path, db)

    raw = db.transaction()
    with pytest.raises(ValueError, match="Transaction not in progress"):
        db.collection("artifacts").document("linas-ai-bot-backend").collection("meta_deletion_requests").document(
            "c" * 32
        ).get(transaction=raw)

    created = _get_or_create_shared_request(
        bindings=(_DeletionBindingScope("binding-target", 1),),
        **_create_kwargs(db),
    )
    assert created.generation == 1
    assert created.state == "pending"
    assert created.coordinator_state == "pending"
    assert created.current_bindings == (_DeletionBindingScope("binding-target", 1),)

    merged = _get_or_create_shared_request(
        bindings=(
            _DeletionBindingScope("binding-other", 4),
            _DeletionBindingScope("binding-target", 2),
        ),
        **_create_kwargs(db),
    )
    assert merged.confirmation_code == created.confirmation_code
    assert merged.generation == 2
    assert {item.binding_id for item in merged.bindings} == {"binding-target", "binding-other"}
    assert merged.current_bindings == (
        _DeletionBindingScope("binding-other", 4),
        _DeletionBindingScope("binding-target", 2),
    )

    updated = _mark_coordinator_completed(
        db,
        merged,
        revoked_bindings=1,
        shared_redacted_documents=0,
        current_bindings=merged.current_bindings,
    )
    assert updated.generation == 2
    assert updated.coordinator_state == "completed"
    assert updated.state == "pending"
    assert updated.revoked_bindings == 1

    pending, local_redacted = _sanitize_local_and_ack(db, updated)
    assert local_redacted == 0
    assert pending.state == "pending"
    request = _shared_request(db)
    assert request.collection("node_acks").document("node01").get().exists
    assert not request.collection("node_acks").document("node02").get().exists

    request.collection("node_acks").document("node02").set(
        {
            "schema_version": 1,
            "node_id": "node02",
            "status": "completed",
            "request_generation": updated.generation,
            "acknowledged_at": 1_800_000_000,
            "local_redacted_documents": 0,
            "local_blockers": 0,
            "local_remaining_changes": 0,
        }
    )
    finalized = _finalize_shared_request(db, updated.confirmation_code)
    assert finalized.state == "completed"
    assert finalized.generation == 2
    assert request.data["state"] == "completed"
    assert request.data["coordinator_state"] == "completed"
