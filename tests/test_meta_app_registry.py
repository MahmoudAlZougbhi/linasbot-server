"""Two-app Meta registry: classification, encryption, exclusivity, and concurrency."""

from __future__ import annotations

import hashlib
import hmac
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
    get_meta_app_configs,
    identify_signed_meta_app,
    verify_any_meta_challenge_token,
)
from tests.meta_app_registry_helpers import _credential

pytest_plugins = ("tests.meta_app_registry_fixtures",)


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
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )

    assert [binding.binding_id for binding in revoked] == [app_b.binding_id]
    refreshed = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert refreshed[app_b.binding_id].status == "disconnected"
    assert refreshed[app_a.binding_id].status == "active"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(refreshed[app_b.binding_id])
    assert registry.get_credential(refreshed[app_a.binding_id]).token_app_id == configs[APP_A_KEY].app_id


def test_deauthorization_isolates_same_numeric_owner_id_by_auth_flow(
    registry: MetaAppRegistry,
) -> None:
    app_a_id = get_meta_app_configs()[APP_A_KEY].app_id
    facebook = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner",
    )
    instagram = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        page_id="",
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="direct-instagram-token",
            token_app_id="1035856539045307",
            token_profile_id=LINAS_INSTAGRAM_ACCOUNT_ID,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
            authorized_meta_user_id="112233445566",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        auth_flow="instagram_login",
    )

    found = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )
    revoked = registry.revoke_authorization(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )
    disconnected_found = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
    )
    instagram_found = registry.find_authorization_bindings(
        app_key=APP_A_KEY,
        auth_flow="instagram_login",
        authorized_meta_user_id="112233445566",
    )

    assert [binding.binding_id for binding in found] == [facebook.binding_id]
    assert [binding.binding_id for binding in revoked] == [facebook.binding_id]
    assert [binding.binding_id for binding in disconnected_found] == [facebook.binding_id]
    assert [binding.binding_id for binding in instagram_found] == [instagram.binding_id]
    refreshed = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert refreshed[facebook.binding_id].status == "disconnected"
    assert refreshed[instagram.binding_id].status == "active"
    assert registry.get_credential(refreshed[instagram.binding_id]).access_token == "direct-instagram-token"


def test_delayed_deauthorization_does_not_revoke_newer_reconnect(
    registry: MetaAppRegistry,
) -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    old = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=replace(
            _credential(app_id, LINAS_PAGE_ID),
            authorization_started_at=100.0,
        ),
        actor_id="owner",
    )
    new_page_id = "445566778899"
    newer = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=new_page_id,
        page_id=new_page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=replace(
            _credential(app_id, new_page_id),
            authorization_started_at=300.0,
        ),
        actor_id="owner",
    )

    revoked = registry.revoke_authorization(
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        authorized_meta_user_id="112233445566",
        authorized_before=200.0,
    )

    assert [binding.binding_id for binding in revoked] == [old.binding_id]
    refreshed = {binding.binding_id: binding for binding in registry.list_bindings()}
    assert refreshed[old.binding_id].status == "disconnected"
    assert refreshed[newer.binding_id].status == "active"
    assert registry.get_credential(refreshed[newer.binding_id]).authorization_started_at == 300.0


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
