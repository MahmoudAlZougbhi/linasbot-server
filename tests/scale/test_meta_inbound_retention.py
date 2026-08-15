from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import services.scale.inbound_event_store as event_store
from services.meta_inbound_retention import (
    inbound_redaction_has_blockers,
    redact_expired_terminal_inbound_events,
    redact_inbound_events_for_bindings,
)


def _ledger(*, event_id: str, state: str, binding_id: str, updated_at: float = 10.0) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "kind": "meta_dm",
        "tenant_id": "linas",
        "claim_namespace": "meta_social_dm_global",
        "claim_key": f"instagram:account:{event_id}",
        "state": state,
        "created_at": 1.0,
        "updated_at": updated_at,
        "payload": {
            "sender_id": "customer-123",
            "sender_username": "private-handle",
            "text": "private message",
        },
        "settings_snapshot": {
            "binding_id": binding_id,
            "tenant_id": "linas",
            "page_access_token": "must-disappear",
        },
        "binding_snapshot": {
            "binding_id": binding_id,
            "tenant_id": "linas",
            "channel": "instagram",
            "app_key": "linas_first_party",
            "auth_flow": "instagram_login",
            "asset_id": "private-asset-id",
        },
        "conversation_key": "linas:instagram:customer-123",
        "queue_job_id": "job-1",
        "last_error": "provider detail",
        "future_private_field": {"secret": "must-disappear"},
    }


def _write(root: Path, raw: dict[str, Any]) -> Path:
    path = root / f"{raw['event_id']}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


class _Snapshot:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = copy.deepcopy(data)
        self.reference = self

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)

    def set(self, document: dict[str, Any]) -> None:
        self.data = copy.deepcopy(document)


class _Collection:
    def __init__(self, snapshots: list[_Snapshot]) -> None:
        self.snapshots = snapshots

    def stream(self) -> list[_Snapshot]:
        return self.snapshots


class _Document:
    def __init__(self, collection: _Collection) -> None:
        self._collection = collection

    def document(self, _name: str) -> _Document:
        return self

    def collection(self, _name: str) -> _Collection:
        return self._collection


class _Firestore:
    def __init__(self, snapshots: list[_Snapshot]) -> None:
        self._collection = _Collection(snapshots)

    def collection(self, _name: str) -> _Document:
        return _Document(self._collection)


def test_retention_redacts_only_expired_terminal_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbound_events"
    root.mkdir()
    expired = _write(root, _ledger(event_id="ibe_expired", state="completed", binding_id="binding-1"))
    active = _write(root, _ledger(event_id="ibe_active", state="failed", binding_id="binding-1"))
    recent = _write(
        root,
        _ledger(event_id="ibe_recent", state="dead_letter", binding_id="binding-1", updated_at=950.0),
    )
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)

    stats = redact_expired_terminal_inbound_events(
        apply=True,
        include_firestore=False,
        retention_seconds=100.0,
        now=1000.0,
    )

    redacted = json.loads(expired.read_text(encoding="utf-8"))
    assert redacted["payload"] == {}
    assert redacted["claim_key"] == ""
    assert redacted["conversation_key"] == ""
    assert redacted["binding_snapshot"] == {
        "binding_id": "binding-1",
        "channel": "instagram",
        "app_key": "linas_first_party",
        "auth_flow": "instagram_login",
    }
    assert "future_private_field" not in redacted
    assert redacted["tenant_id"] == ""
    assert "private" not in json.dumps(redacted)
    assert json.loads(active.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert json.loads(recent.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert stats["local_redacted"] == 1
    assert stats["local_active_matches"] == 0


def test_authorization_redaction_preserves_active_records_and_blocks_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.utils

    root = tmp_path / "inbound_events"
    root.mkdir()
    active_path = _write(root, _ledger(event_id="ibe_active", state="processing", binding_id="binding-target"))
    unrelated_path = _write(root, _ledger(event_id="ibe_other", state="completed", binding_id="binding-other"))
    firestore_active = _Snapshot(_ledger(event_id="ibe_fs_active", state="accepted", binding_id="binding-target"))
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: _Firestore([firestore_active]))

    stats = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=True,
        include_firestore=True,
        now=1000.0,
    )

    assert stats["local_active_matches"] == 1
    assert stats["firestore_active_matches"] == 1
    assert inbound_redaction_has_blockers(stats, require_firestore=True) is True
    assert json.loads(active_path.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert firestore_active.data["payload"]["text"] == "private message"
    assert json.loads(unrelated_path.read_text(encoding="utf-8"))["payload"]["text"] == "private message"


def test_authorization_redaction_updates_matching_terminal_rows_in_both_stores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.utils

    root = tmp_path / "inbound_events"
    root.mkdir()
    matching_path = _write(root, _ledger(event_id="ibe_match", state="completed", binding_id="binding-target"))
    unrelated_path = _write(root, _ledger(event_id="ibe_other", state="completed", binding_id="binding-other"))
    firestore_matching = _Snapshot(_ledger(event_id="ibe_fs_match", state="dead_letter", binding_id="binding-target"))
    firestore_unrelated = _Snapshot(_ledger(event_id="ibe_fs_other", state="completed", binding_id="binding-other"))
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(
        utils.utils,
        "get_firestore_db",
        lambda: _Firestore([firestore_matching, firestore_unrelated]),
    )

    stats = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=True,
        include_firestore=True,
        now=1000.0,
    )

    assert inbound_redaction_has_blockers(stats, require_firestore=True) is False
    assert stats["local_redacted"] == 1
    assert stats["firestore_redacted"] == 1
    local_matching = json.loads(matching_path.read_text(encoding="utf-8"))
    assert local_matching["payload"] == {}
    assert "future_private_field" not in local_matching
    assert firestore_matching.data["payload"] == {}
    assert "future_private_field" not in firestore_matching.data
    assert json.loads(unrelated_path.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert firestore_unrelated.data["payload"]["text"] == "private message"


def test_malformed_local_row_is_a_fail_closed_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbound_events"
    root.mkdir()
    (root / "ibe_malformed.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)

    stats = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=False,
        include_firestore=False,
    )

    assert stats["local_errors"] == 1
    assert inbound_redaction_has_blockers(stats, require_firestore=False) is True


def test_orphan_atomic_payload_blocks_dry_run_and_is_removed_under_apply_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbound_events"
    root.mkdir()
    orphan = root / ".ibe_crash.json.123.456.tmp"
    orphan.write_text(json.dumps({"payload": {"text": "private orphan"}}), encoding="utf-8")
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)

    preflight = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=False,
        include_firestore=False,
    )
    assert preflight["local_orphan_files"] == 1
    assert inbound_redaction_has_blockers(preflight, require_firestore=False) is True

    applied = redact_inbound_events_for_bindings(
        {"binding-target"},
        apply=True,
        include_firestore=False,
    )
    assert applied["local_orphans_removed"] == 1
    assert applied["local_orphan_files"] == 0
    assert orphan.exists() is False
    assert inbound_redaction_has_blockers(applied, require_firestore=False) is False
