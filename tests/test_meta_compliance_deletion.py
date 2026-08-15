"""Authenticated Meta authorization deletion and route-inventory tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import services.durable_event_claim as durable_claims
import services.scale.inbound_event_store as event_store
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
)
from services.meta_data_deletion import delete_meta_social_user_data, read_deletion_status
from tests.meta_compliance_helpers import (
    APP_A_ENV,
    APP_SECRET,
    _FakeDocument,
    _FakeFirestore,
)

APP_A_ID = "2963733803971681"
INSTAGRAM_APP_ID = "1035856539045307"
INSTAGRAM_APP_SECRET = "instagram-login-secret-for-tests"


class _Registry:
    def __init__(self, *bindings: SimpleNamespace) -> None:
        self.bindings = list(bindings)
        self.revocation_calls: list[dict[str, str]] = []

    def find_authorization_bindings(
        self,
        *,
        app_key: str,
        auth_flow: str,
        authorized_meta_user_id: str,
    ) -> list[SimpleNamespace]:
        assert authorized_meta_user_id == "123456789"
        return [binding for binding in self.bindings if binding.app_key == app_key and binding.auth_flow == auth_flow]

    def revoke_authorization(
        self,
        *,
        app_key: str,
        auth_flow: str,
        authorized_meta_user_id: str,
        actor_id: str,
    ) -> list[SimpleNamespace]:
        self.revocation_calls.append(
            {
                "app_key": app_key,
                "auth_flow": auth_flow,
                "authorized_meta_user_id": authorized_meta_user_id,
                "actor_id": actor_id,
            }
        )
        revoked: list[SimpleNamespace] = []
        for binding in self.bindings:
            if binding.app_key == app_key and binding.auth_flow == auth_flow and binding.status != "disconnected":
                binding.status = "disconnected"
                revoked.append(binding)
        return revoked

    def revoke_authorization_exact(
        self,
        *,
        app_key: str,
        auth_flow: str,
        authorized_meta_user_id: str,
        expected_bindings: dict[str, int],
        actor_id: str,
    ) -> list[SimpleNamespace]:
        matching = {
            binding.binding_id: binding
            for binding in self.bindings
            if binding.app_key == app_key and binding.auth_flow == auth_flow
        }
        assert set(matching) == set(expected_bindings)
        for binding_id, expected_generation in expected_bindings.items():
            binding = matching[binding_id]
            assert binding.generation in {expected_generation, expected_generation + 1}
        revoked = self.revoke_authorization(
            app_key=app_key,
            auth_flow=auth_flow,
            authorized_meta_user_id=authorized_meta_user_id,
            actor_id=actor_id,
        )
        for binding in revoked:
            binding.generation += 1
        return revoked


def _binding(
    binding_id: str = "binding-target",
    *,
    auth_flow: str = "facebook_login",
) -> SimpleNamespace:
    return SimpleNamespace(
        binding_id=binding_id,
        app_key=APP_A_KEY,
        auth_flow=auth_flow,
        status="active",
        generation=1,
    )


def _ledger(
    *,
    event_id: str,
    binding_id: str,
    state: str = "completed",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "kind": "meta_dm",
        "tenant_id": "linas",
        "claim_namespace": "meta_social_dm_global",
        "claim_key": f"instagram:account:{event_id}",
        "state": state,
        "created_at": 10.0,
        "updated_at": 20.0,
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
            "app_key": APP_A_KEY,
            "auth_flow": "facebook_login",
            "asset_id": "private-asset-id",
        },
        "conversation_key": "linas:instagram:customer-123",
        "queue_job_id": "job-private",
        "last_error": "provider-private-detail",
    }


def _write_ledger(root: Path, raw: dict[str, Any]) -> Path:
    path = root / f"{raw['event_id']}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _patch_deletion_stores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db: _FakeFirestore | None,
) -> Path:
    import services.meta_data_deletion as deletion_service
    import utils.utils

    ledger_root = tmp_path / "inbound_events"
    ledger_root.mkdir()
    claims_root = tmp_path / "claim_logs"
    (claims_root / "durable_claims").mkdir(parents=True)
    monkeypatch.setattr(event_store, "_store_dir", lambda: ledger_root)
    monkeypatch.setattr(
        durable_claims,
        "_claims_dir",
        lambda: (claims_root / "durable_claims"),
    )
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_LOCK_DIR", tmp_path / "deletion_runtime")
    return ledger_root


def _facebook_delete(registry: Any):
    return delete_meta_social_user_data(
        "123456789",
        APP_SECRET,
        app_key=APP_A_KEY,
        signing_app_id=APP_A_ID,
        auth_flow="facebook_login",
        registry=registry,
    )


def _deletion_documents(db: _FakeFirestore, collection: str) -> list[_FakeDocument]:
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    return [document for document in app.collection(collection).documents.values() if document.exists]


def _only_status(db: _FakeFirestore) -> dict[str, Any]:
    documents = _deletion_documents(db, "meta_deletion_requests")
    assert len(documents) == 1
    return documents[0].data


@pytest.fixture(autouse=True)
def _configure_app_a(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in APP_A_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("META_DELETION_NODE_ID", "node01")
    monkeypatch.setenv("META_DELETION_REQUIRED_NODES", "node01")


def test_deletion_revokes_exact_authorization_and_redacts_linked_terminal_ledgers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    inbound = app.collection("inbound_events")
    target_event_id = "ibe_" + "1" * 40
    other_event_id = "ibe_" + "2" * 40
    firestore_target = _FakeDocument(
        f"{inbound.path}/{target_event_id}",
        data=_ledger(event_id=target_event_id, binding_id="binding-target"),
    )
    firestore_unrelated = _FakeDocument(
        f"{inbound.path}/{other_event_id}",
        data=_ledger(event_id=other_event_id, binding_id="binding-other"),
    )
    inbound.documents[target_event_id] = firestore_target
    inbound.documents[other_event_id] = firestore_unrelated

    binding_digest = durable_claims.meta_claim_binding_digest("binding-target")
    shared_claim = app.collection("meta_social_dm_global_claims").document("claim-target")
    shared_claim.set({"binding_id_sha256": binding_digest, "status": "completed"})
    ai_claim = app.collection("ai_turn_claims").document("ai-target")
    ai_claim.set({"binding_id_sha256": binding_digest, "status": "completed"})
    outbound_attempt = app.collection("meta_outbound_attempts").document(target_event_id)
    outbound_attempt.set({"event_id": target_event_id, "status": "accepted"})
    unrelated_claim = app.collection("ai_turn_claims").document("ai-other")
    unrelated_claim.set({"binding_id_sha256": durable_claims.meta_claim_binding_digest("binding-other")})

    users = app.collection("users")
    end_customer = users.document("facebook:123456789")
    end_customer.exists = True
    end_customer.data = {"conversation": "must-not-be-selected-from-authorizer-id"}

    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    local_target = _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_local_target", binding_id="binding-target"),
    )
    local_unrelated = _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_local_other", binding_id="binding-other"),
    )
    local_claim = durable_claims._file_claim_path("ai_turn_claims", "claim-target")
    local_claim.parent.mkdir(parents=True, exist_ok=True)
    local_claim.write_text(json.dumps({"binding_id_sha256": binding_digest}), encoding="utf-8")
    registry = _Registry(_binding())

    result = _facebook_delete(registry)

    assert result.revoked_bindings == 1
    assert result.redacted_ledger_documents == 2
    assert result.deleted_user_documents == 0
    assert result.deleted_nested_documents == 0
    assert result.deleted_index_documents == 0
    assert json.loads(local_target.read_text(encoding="utf-8"))["payload"] == {}
    assert firestore_target.data["payload"] == {}
    assert json.loads(local_unrelated.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert firestore_unrelated.data["payload"]["text"] == "private message"
    assert shared_claim.exists is False
    assert ai_claim.exists is False
    assert outbound_attempt.exists is False
    assert unrelated_claim.exists is True
    assert local_claim.exists() is False
    assert end_customer.exists is True
    assert end_customer.data["conversation"] == "must-not-be-selected-from-authorizer-id"
    assert registry.revocation_calls == [
        {
            "app_key": APP_A_KEY,
            "auth_flow": "facebook_login",
            "authorized_meta_user_id": "123456789",
            "actor_id": "meta-data-deletion",
        }
    ]
    status = read_deletion_status(result.confirmation_code)
    assert status is not None
    assert status["status"] == "completed"
    assert status["revoked_bindings"] == 1
    assert status["redacted_ledger_documents"] == 2
    serialized = json.dumps(_only_status(db), sort_keys=True)
    assert "123456789" not in serialized
    assert "must-disappear" not in serialized


def test_repeated_deletion_request_is_idempotent_for_the_same_signing_domain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_local_target", binding_id="binding-target"),
    )
    registry = _Registry(_binding())

    first = _facebook_delete(registry)
    second = _facebook_delete(registry)

    assert first.confirmation_code == second.confirmation_code
    assert first.revoked_bindings == 1
    assert second.revoked_bindings == 0
    assert second.redacted_ledger_documents == 0
    status = read_deletion_status(second.confirmation_code)
    assert status is not None and status["status"] == "completed"


def test_simultaneous_callbacks_share_one_confirmation_and_do_not_collide(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_local_target", binding_id="binding-target"),
    )
    registry = _Registry(_binding())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: _facebook_delete(registry), range(2)))

    assert results[0].confirmation_code == results[1].confirmation_code
    assert len(_deletion_documents(db, "meta_deletion_subject_index")) == 1
    assert len(_deletion_documents(db, "meta_deletion_requests")) == 1
    status = read_deletion_status(results[0].confirmation_code)
    assert status is not None and status["status"] == "completed"


def test_same_numeric_authorizer_is_namespaced_by_signing_app_and_flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    _patch_deletion_stores(monkeypatch, tmp_path, db)
    registry = _Registry()

    facebook = _facebook_delete(registry)
    instagram = delete_meta_social_user_data(
        "123456789",
        INSTAGRAM_APP_SECRET,
        app_key=APP_A_KEY,
        signing_app_id=INSTAGRAM_APP_ID,
        auth_flow="instagram_login",
        registry=registry,
    )

    assert facebook.confirmation_code != instagram.confirmation_code
    assert len(_deletion_documents(db, "meta_deletion_subject_index")) == 2
    assert read_deletion_status(facebook.confirmation_code)["status"] == "no_data"
    assert read_deletion_status(instagram.confirmation_code)["status"] == "no_data"
    assert [call["auth_flow"] for call in registry.revocation_calls] == [
        "facebook_login",
        "instagram_login",
    ]


def test_old_facebook_authorizer_deletion_preserves_new_authorizer_lineage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="deletion-lineage-master-secret-tests-123456789",
    )
    scopes = (
        "pages_show_list",
        "pages_manage_metadata",
        "pages_read_engagement",
        "pages_messaging",
    )
    old = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id="445566778899",
        page_id="445566778899",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="old-owner-token",
            token_app_id=APP_A_ID,
            token_profile_id="445566778899",
            scopes=scopes,
            authorized_meta_user_id="123456789",
        ),
        actor_id="old-owner",
    )
    staged = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id="445566778899",
        page_id="445566778899",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="new-owner-token",
            token_app_id=APP_A_ID,
            token_profile_id="445566778899",
            scopes=scopes,
            authorized_meta_user_id="998877665",
        ),
        actor_id="new-owner",
        status="testing",
        create_new_binding=True,
    )
    new = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="new-owner",
        expected_generation=staged.generation,
        replace_existing=True,
    )
    old_event = _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_old_owner", binding_id=old.binding_id),
    )
    new_event = _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_new_owner", binding_id=new.binding_id),
    )

    result = _facebook_delete(registry)

    assert result.revoked_bindings == 1
    assert result.redacted_ledger_documents == 1
    assert json.loads(old_event.read_text(encoding="utf-8"))["payload"] == {}
    assert json.loads(new_event.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    refreshed = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert refreshed[old.binding_id].status == "disconnected"
    assert refreshed[new.binding_id].status == "active"
    assert registry.get_credential(refreshed[new.binding_id]).access_token == "new-owner-token"


def test_active_local_event_keeps_shared_request_pending_until_node_can_ack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    active = _write_ledger(
        ledger_root,
        _ledger(
            event_id="ibe_local_active",
            binding_id="binding-target",
            state="processing",
        ),
    )
    registry = _Registry(_binding())

    result = _facebook_delete(registry)

    assert len(registry.revocation_calls) == 1
    assert json.loads(active.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert read_deletion_status(result.confirmation_code)["status"] == "pending"


def test_no_data_is_not_reported_when_a_required_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_deletion_stores(monkeypatch, tmp_path, None)
    registry = _Registry()

    with pytest.raises(RuntimeError, match="store is unavailable"):
        _facebook_delete(registry)

    assert registry.revocation_calls == []


def test_partial_redaction_error_marks_request_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    inbound = app.collection("inbound_events")
    firestore_target = _FakeDocument(
        f"{inbound.path}/ibe_firestore_target",
        data=_ledger(event_id="ibe_firestore_target", binding_id="binding-target"),
    )
    inbound.documents["ibe_firestore_target"] = firestore_target
    monkeypatch.setattr(
        firestore_target,
        "set",
        lambda _document: (_ for _ in ()).throw(OSError("simulated write failure")),
    )
    ledger_root = _patch_deletion_stores(monkeypatch, tmp_path, db)
    local_target = _write_ledger(
        ledger_root,
        _ledger(event_id="ibe_local_target", binding_id="binding-target"),
    )
    registry = _Registry(_binding())

    with pytest.raises(RuntimeError, match="did not complete"):
        _facebook_delete(registry)

    assert len(registry.revocation_calls) == 1
    assert json.loads(local_target.read_text(encoding="utf-8"))["payload"]["text"] == "private message"
    assert firestore_target.data["payload"]["text"] == "private message"
    status = _only_status(db)
    assert status["state"] == "failed"
    assert status["safe_error"] == "shared_redaction"
    assert "simulated write failure" not in json.dumps(status)


def test_production_main_route_inventory_is_explicit() -> None:
    import main

    main_source = Path("main.py").read_text(encoding="utf-8")
    for route_module in (
        "modules.webhook_handlers",
        "modules.meta_messaging_webhook",
        "modules.meta_compliance",
        "modules.dashboard_api",
        "modules.auth_api",
        "modules.live_chat_api",
    ):
        assert f"import {route_module}" in main_source
    registered_paths = {getattr(route, "path", "") for route in main.app.routes}
    assert {
        "/api/health",
        "/api/ready",
        "/api/auth/login",
        "/webhook",
        "/webhook/meta-messaging",
        "/privacy-policy",
        "/terms",
        "/data-deletion",
        "/oauth/meta/deauthorize",
        "/oauth/meta/data-deletion",
        "/oauth/instagram/deauthorize",
        "/oauth/instagram/data-deletion",
        "/data-deletion/status/{confirmation_code}",
        "/meta/deauthorize",
    } <= registered_paths
