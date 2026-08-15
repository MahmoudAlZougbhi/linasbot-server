from __future__ import annotations

import json
from pathlib import Path

import pytest

import services.durable_event_claim as claims
import services.scale.inbound_event_store as event_store
from services.meta_claim_data_deletion import (
    MetaClaimDeletionActiveError,
    MetaClaimDeletionError,
    apply_shared_meta_claim_deletion_plan,
    build_local_meta_claim_deletion_plan,
    build_shared_meta_claim_deletion_plan,
    delete_and_verify_local_meta_claims,
)
from tests.meta_compliance_helpers import _FakeFirestore


def _inbound(binding_id: str, event_id: str, claim_key: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "kind": "meta_dm",
        "tenant_id": "linas",
        "claim_key": claim_key,
        "payload": {
            "channel": "facebook",
            "sender_id": "sender-private-1",
            "message_id": "provider-private-mid-1",
        },
        "settings_snapshot": {"binding_id": binding_id, "page_id": "page-1"},
        "binding_snapshot": {
            "binding_id": binding_id,
            "tenant_id": "linas",
            "channel": "facebook",
            "asset_id": "page-1",
        },
    }


def test_shared_claim_deletion_selects_current_and_historical_rows_only() -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    binding_id = "binding-delete-1"
    event_id = "ibe_" + "a" * 40
    claim_key = "facebook:page-1:provider-private-mid-1"
    app.collection("inbound_events").document(event_id).set(_inbound(binding_id, event_id, claim_key))

    global_id = claims._firestore_claim_document_id("meta_social_dm_global", claim_key)
    app.collection("meta_social_dm_global_claims").document(global_id).set(
        {"status": "completed", "key_prefix": claim_key}
    )
    app.collection("ai_turn_claims").document("historical-ai").set(
        {
            "stable_identity": "facebook:sender-private-1",
            "inbound_ids_preview": "provider-private-mid-1",
        }
    )
    app.collection("ai_turn_claims").document("current-ai").set(
        {"binding_id_sha256": claims.meta_claim_binding_digest(binding_id), "status": "completed"}
    )
    app.collection("ai_turn_claims_file").document("scoped-legacy-ai").set(
        {"key_prefix": "facebook:page-1:sender-private-1\0textbody\0opaque\0slot1"}
    )
    app.collection("meta_outbound_attempts").document(event_id).set({"status": "accepted"})
    unrelated = app.collection("ai_turn_claims").document("unrelated")
    unrelated.set({"stable_identity": "facebook:someone-else", "status": "completed"})
    substring_unrelated = app.collection("ai_turn_claims_file").document("substring-unrelated")
    substring_unrelated.set({"key_prefix": "someone-else\0mids\0prefix-provider-private-mid-1-suffix"})

    plan = build_shared_meta_claim_deletion_plan(db, {binding_id})
    assert set(plan.shared_documents) == {
        ("meta_social_dm_global_claims", global_id),
        ("ai_turn_claims", "historical-ai"),
        ("ai_turn_claims", "current-ai"),
        ("ai_turn_claims_file", "scoped-legacy-ai"),
        ("meta_outbound_attempts", event_id),
    }
    stats = apply_shared_meta_claim_deletion_plan(db, plan)
    assert stats == {"matched": 5, "changed": 5, "remaining": 0, "errors": 0}
    assert unrelated.exists is True
    assert substring_unrelated.exists is True


def test_shared_claim_deletion_refuses_live_provider_attempt() -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    binding_id = "binding-live-send"
    event_id = "ibe_" + "d" * 40
    app.collection("inbound_events").document(event_id).set(_inbound(binding_id, event_id, "facebook:page:mid"))
    app.collection("meta_outbound_attempts").document(event_id).set(
        {
            "status": "sending",
            "binding_id_sha256": claims.meta_claim_binding_digest(binding_id),
        }
    )

    with pytest.raises(MetaClaimDeletionActiveError, match="active"):
        build_shared_meta_claim_deletion_plan(db, {binding_id})


@pytest.fixture()
def local_claim_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    ledger = tmp_path / "inbound_events"
    claims_root = tmp_path / "logs"
    ledger.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: ledger)
    monkeypatch.setattr(claims, "LOGS_DIR", claims_root)
    monkeypatch.setattr(claims, "ensure_dirs", lambda: claims_root.mkdir(parents=True, exist_ok=True))
    return ledger, claims_root


def test_local_claim_deletion_removes_exact_files_and_preserves_unrelated(local_claim_store: tuple[Path, Path]) -> None:
    ledger, _claims_root = local_claim_store
    binding_id = "binding-delete-local"
    event_id = "ibe_" + "b" * 40
    claim_key = "facebook:page-1:provider-private-mid-1"
    (ledger / f"{event_id}.json").write_text(
        json.dumps(_inbound(binding_id, event_id, claim_key)),
        encoding="utf-8",
    )
    global_path = claims._file_claim_path("meta_social_dm_global", claim_key)
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text(json.dumps({"key_prefix": claim_key}), encoding="utf-8")
    ai_path = claims._file_claim_path("ai_turn_claims", "opaque-key")
    ai_path.parent.mkdir(parents=True, exist_ok=True)
    ai_path.write_text(
        json.dumps({"binding_id_sha256": claims.meta_claim_binding_digest(binding_id)}),
        encoding="utf-8",
    )
    unrelated = claims._file_claim_path("ai_turn_claims", "unrelated")
    unrelated.write_text(json.dumps({"binding_id_sha256": "f" * 64}), encoding="utf-8")

    plan = build_local_meta_claim_deletion_plan({binding_id})
    assert set(plan.local_files) == {global_path, ai_path}
    stats = delete_and_verify_local_meta_claims({binding_id})
    assert stats == {"matched": 2, "changed": 2, "remaining": 0, "errors": 0}
    assert unrelated.is_file()


def test_local_claim_deletion_fails_closed_on_unknown_orphan(local_claim_store: tuple[Path, Path]) -> None:
    ledger, claims_root = local_claim_store
    binding_id = "binding-delete-local"
    event_id = "ibe_" + "c" * 40
    (ledger / f"{event_id}.json").write_text(
        json.dumps(_inbound(binding_id, event_id, "facebook:claim")),
        encoding="utf-8",
    )
    orphan = claims_root / "durable_claims" / "ai_turn_claims" / ".orphan.tmp"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("partial", encoding="utf-8")

    with pytest.raises(MetaClaimDeletionError, match="orphan"):
        delete_and_verify_local_meta_claims({binding_id})
