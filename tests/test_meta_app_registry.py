"""Two-app Meta registry, encryption, exclusivity, OAuth state, and routing proofs."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from modules.api_security import is_social_user_id
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaCredentialCipher,
    MetaCredentialError,
    MetaOAuthStateError,
    get_meta_app_configs,
    get_meta_registry_readiness,
    identify_signed_meta_app,
    verify_any_meta_challenge_token,
)
from services.meta_multi_app_router import resolve_registry_events
from services.social_contact_routing import resolve_social_whatsapp_number

ALL_MESSAGING_SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


@pytest.fixture
def meta_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-for-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-for-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-for-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-for-tests")
    monkeypatch.setenv("META_APP_B_LOGIN_CONFIG_ID", "config-for-tests")
    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "registry-master-secret-used-only-in-tests-123456789")
    monkeypatch.delenv("META_APP_B_LINAS_CUTOVER_APPROVED", raising=False)


@pytest.fixture
def registry(tmp_path: Path, meta_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="registry-master-secret-used-only-in-tests-123456789",
    )


def _credential(app_id: str, page_id: str, *, scopes: tuple[str, ...] = ALL_MESSAGING_SCOPES) -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token=f"sensitive-token-{app_id}-{page_id}",
        token_app_id=app_id,
        token_profile_id=page_id,
        scopes=scopes,
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id="112233445566",
    )


def _page_payload(*, page_id: str, message_id: str = "mid-1") -> dict[str, object]:
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": page_id},
                        "message": {"mid": message_id, "text": "hello"},
                    }
                ],
            }
        ],
    }


def test_app_classifications_and_exact_signature_selection(meta_env: None) -> None:
    configs = get_meta_app_configs()
    assert configs[APP_A_KEY].classification == "own_business"
    assert configs[APP_A_KEY].app_id == "2963733803971681"
    assert configs[APP_B_KEY].classification == "tech_provider"

    body = b'{"object":"page","entry":[]}'
    digest = hmac.new(b"app-b-secret-for-tests", body, hashlib.sha256).hexdigest()
    selected = identify_signed_meta_app(body, f"sha256={digest}")
    assert selected is not None and selected.key == APP_B_KEY
    assert identify_signed_meta_app(body, "sha256=deadbeef") is None
    assert verify_any_meta_challenge_token("verify-a-for-tests") is True
    assert verify_any_meta_challenge_token("verify-b-for-tests") is True
    assert verify_any_meta_challenge_token("wrong") is False


def test_tenant_namespaced_social_identity_remains_operator_read_only() -> None:
    assert is_social_user_id("facebook:123456") is True
    assert is_social_user_id("instagram:123456") is True
    assert is_social_user_id("external-clinic:facebook:123456") is True
    assert is_social_user_id("external-clinic:instagram:123456") is True
    assert is_social_user_id("external-clinic:whatsapp:123456") is False


def test_invalid_tenant_identifier_is_rejected(registry: MetaAppRegistry) -> None:
    app_b_id = get_meta_app_configs()[APP_B_KEY].app_id
    with pytest.raises(MetaBindingConflictError, match="tenant identifier"):
        registry.activate_binding(
            tenant_id="../another-tenant",
            channel="facebook",
            asset_id="998877001122",
            page_id="998877001122",
            instagram_account_id="",
            app_key=APP_B_KEY,
            credential=_credential(app_b_id, "998877001122"),
            actor_id="owner",
            status="testing",
        )


def test_cipher_round_trip_and_tamper_rejection() -> None:
    cipher = MetaCredentialCipher("a-long-enough-master-secret-for-unit-tests-only")
    sealed = cipher.seal({"access_token": "private-token"}, aad="binding-aad")
    assert "private-token" not in sealed
    assert cipher.open(sealed, aad="binding-aad") == {"access_token": "private-token"}
    with pytest.raises(MetaCredentialError):
        cipher.open(sealed[:-1] + ("A" if sealed[-1] != "A" else "B"), aad="binding-aad")


def test_registry_encrypts_tokens_and_redacts_audit(registry: MetaAppRegistry, tmp_path: Path) -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    binding = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_id, LINAS_PAGE_ID),
        actor_id="owner-1",
    )
    stored = (tmp_path / "registry.json").read_text(encoding="utf-8")
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sensitive-token" not in stored
    assert "sensitive-token" not in audit
    assert "owner-1" not in audit
    assert LINAS_PAGE_ID not in audit
    assert registry.get_credential(binding).token_profile_id == LINAS_PAGE_ID
    assert (tmp_path / "registry.json").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "audit.jsonl").stat().st_mode & 0o777 == 0o600


def test_deauthorization_disconnects_only_matching_app_and_destroys_token(
    registry: MetaAppRegistry,
) -> None:
    configs = get_meta_app_configs()
    app_b = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id="445566778899",
        page_id="445566778899",
        instagram_account_id="",
        app_key=APP_B_KEY,
        credential=_credential(configs[APP_B_KEY].app_id, "445566778899"),
        actor_id="owner-a@example.com",
        status="testing",
    )
    app_a = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(configs[APP_A_KEY].app_id, LINAS_PAGE_ID),
        actor_id="owner",
    )

    revoked = registry.revoke_authorization(
        app_key=APP_B_KEY,
        authorized_meta_user_id="112233445566",
    )

    assert [binding.binding_id for binding in revoked] == [app_b.binding_id]
    refreshed = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert refreshed[app_b.binding_id].status == "disconnected"
    assert refreshed[app_a.binding_id].status == "active"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(refreshed[app_b.binding_id])
    assert registry.get_credential(refreshed[app_a.binding_id]).token_app_id == configs[APP_A_KEY].app_id


def test_one_active_app_per_tenant_channel_and_asset(registry: MetaAppRegistry) -> None:
    configs = get_meta_app_configs()
    app_a = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(configs[APP_A_KEY].app_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    assert app_a.active

    with pytest.raises(MetaBindingConflictError):
        registry.activate_binding(
            tenant_id="other-tenant",
            channel="facebook",
            asset_id=LINAS_PAGE_ID,
            page_id=LINAS_PAGE_ID,
            instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
            app_key=APP_B_KEY,
            credential=_credential(configs[APP_B_KEY].app_id, LINAS_PAGE_ID),
            actor_id="owner",
        )

    demo = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_B_KEY,
        credential=_credential(configs[APP_B_KEY].app_id, LINAS_PAGE_ID),
        actor_id="reviewer-demo",
        status="testing",
    )
    assert demo.status == "testing"
    assert registry.get_active_bindings_for_app(APP_B_KEY) == []


def test_concurrent_process_style_activation_keeps_one_asset_owner(
    tmp_path: Path,
    meta_env: None,
) -> None:
    store_path = tmp_path / "shared-registry.json"
    audit_path = tmp_path / "shared-audit.jsonl"
    secret = "shared-registry-concurrency-secret-tests-123456789"
    registries = [MetaAppRegistry(store_path=store_path, audit_path=audit_path, master_secret=secret) for _ in range(2)]
    barrier = threading.Barrier(2)
    page_id = "445500001111"
    apps = get_meta_app_configs()

    def activate(index: int) -> str:
        app_key = APP_A_KEY if index == 0 else APP_B_KEY
        barrier.wait(timeout=5)
        try:
            registries[index].activate_binding(
                tenant_id=f"tenant-{index}",
                channel="facebook",
                asset_id=page_id,
                page_id=page_id,
                instagram_account_id="",
                app_key=app_key,
                credential=_credential(apps[app_key].app_id, page_id),
                actor_id=f"owner-{index}",
            )
            return "active"
        except MetaBindingConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(activate, range(2)))

    assert sorted(results) == ["active", "conflict"]
    active = registries[0].list_bindings(include_inactive=False)
    assert len(active) == 1
    assert active[0].asset_id == page_id


def test_app_b_linas_activation_requires_separate_cutover_flag(registry: MetaAppRegistry) -> None:
    app_b_id = get_meta_app_configs()[APP_B_KEY].app_id
    with pytest.raises(MetaBindingConflictError, match="approved cutover"):
        registry.activate_binding(
            tenant_id="linas",
            channel="instagram",
            asset_id=LINAS_INSTAGRAM_ACCOUNT_ID,
            page_id=LINAS_PAGE_ID,
            instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
            app_key=APP_B_KEY,
            credential=_credential(app_b_id, LINAS_PAGE_ID),
            actor_id="owner",
        )


def test_app_b_external_activation_requires_advanced_access_approval(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_b_id = get_meta_app_configs()[APP_B_KEY].app_id
    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "false")
    with pytest.raises(MetaBindingConflictError, match="Advanced Access"):
        registry.activate_binding(
            tenant_id="tenant-a",
            channel="facebook",
            asset_id="998877001122",
            page_id="998877001122",
            instagram_account_id="",
            app_key=APP_B_KEY,
            credential=_credential(app_b_id, "998877001122"),
            actor_id="owner",
        )


def test_prohibited_non_messaging_scope_is_rejected(registry: MetaAppRegistry) -> None:
    app_a_id = get_meta_app_configs()[APP_A_KEY].app_id
    with pytest.raises(MetaBindingConflictError, match="prohibited"):
        registry.activate_binding(
            tenant_id="linas",
            channel="facebook",
            asset_id=LINAS_PAGE_ID,
            page_id=LINAS_PAGE_ID,
            instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
            app_key=APP_A_KEY,
            credential=_credential(app_a_id, LINAS_PAGE_ID, scopes=ALL_MESSAGING_SCOPES + ("business_management",)),
            actor_id="owner",
        )


def test_replace_and_rollback_restores_previous_provider(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    configs = get_meta_app_configs()
    page_id = "445566778899"
    first = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(configs[APP_A_KEY].app_id, page_id),
        actor_id="owner",
    )
    second = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_B_KEY,
        credential=_credential(configs[APP_B_KEY].app_id, page_id),
        actor_id="owner",
        replace_existing=True,
    )
    assert second.previous_binding_id == first.binding_id
    assert registry.get_active_bindings_for_app(APP_A_KEY) == []
    restored = registry.rollback_binding(second.binding_id, actor_id="owner")
    assert restored.binding_id == first.binding_id
    assert restored.active
    assert registry.get_active_bindings_for_app(APP_B_KEY) == []


def test_staged_lina_cutover_is_explicit_atomic_and_rollback_ready(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = get_meta_app_configs()
    app_a = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(configs[APP_A_KEY].app_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    staged = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_B_KEY,
        credential=_credential(configs[APP_B_KEY].app_id, LINAS_PAGE_ID),
        actor_id="owner",
        status="testing",
    )
    assert staged.previous_binding_id == app_a.binding_id
    assert registry.get_active_bindings_for_app(APP_A_KEY)[0].binding_id == app_a.binding_id
    with pytest.raises(MetaBindingConflictError, match="approved cutover"):
        registry.activate_staged_binding(
            staged.binding_id,
            actor_id="owner",
            replace_existing=True,
        )

    monkeypatch.setenv("META_APP_B_LINAS_CUTOVER_APPROVED", "true")
    activated = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
        replace_existing=True,
    )
    assert activated.active
    assert activated.previous_binding_id == app_a.binding_id
    assert registry.get_active_bindings_for_app(APP_A_KEY) == []
    restored = registry.rollback_binding(activated.binding_id, actor_id="owner")
    assert restored.binding_id == app_a.binding_id
    assert restored.active


def test_oauth_state_is_one_time_and_expires(registry: MetaAppRegistry) -> None:
    registry.store_oauth_state("nonce-hash", {"expires_at": time.time() + 30, "tenant_id": "tenant-a"})
    assert registry.consume_oauth_state("nonce-hash")["tenant_id"] == "tenant-a"
    with pytest.raises(MetaOAuthStateError):
        registry.consume_oauth_state("nonce-hash")

    registry.store_oauth_state("expired", {"expires_at": time.time() - 1})
    with pytest.raises(MetaOAuthStateError):
        registry.consume_oauth_state("expired")


def test_app_b_signature_cannot_route_app_a_active_binding(registry: MetaAppRegistry) -> None:
    configs = get_meta_app_configs()
    registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(configs[APP_A_KEY].app_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    payload = _page_payload(page_id=LINAS_PAGE_ID)
    assert resolve_registry_events(payload, app_config=configs[APP_B_KEY], registry=registry) == []
    routed = resolve_registry_events(payload, app_config=configs[APP_A_KEY], registry=registry)
    assert len(routed) == 1
    assert routed[0].settings.tenant_id == "linas"
    assert routed[0].event["meta_app_key"] == APP_A_KEY
    assert "sensitive-token" not in json.dumps(routed[0].event)


def test_registry_readiness_requires_both_lina_channels_on_app_a(registry: MetaAppRegistry) -> None:
    app_a_id = get_meta_app_configs()[APP_A_KEY].app_id
    registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    ready, checks = get_meta_registry_readiness(registry)
    assert ready is False
    assert checks["linas_facebook_app_a_active"] is True
    assert checks["linas_instagram_app_a_active"] is False

    registry.activate_binding(
        tenant_id="linas",
        channel="instagram",
        asset_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    ready, checks = get_meta_registry_readiness(registry)
    assert ready is True
    assert all(checks.values())


def test_external_tenant_never_inherits_lina_whatsapp_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")
    assert (
        resolve_social_whatsapp_number(
            "SOCIAL_WHATSAPP_BEIRUT_FEMALE",
            tenant_id="external-clinic",
        )
        is None
    )
    assert (
        resolve_social_whatsapp_number(
            "SOCIAL_WHATSAPP_BEIRUT_FEMALE",
            tenant_id="linas",
        )
        == "+96178847527"
    )
