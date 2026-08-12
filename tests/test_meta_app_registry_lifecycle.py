"""Two-app Meta registry: activation policy, OAuth, routing, and cutover."""

from __future__ import annotations

import json
import time

import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    LINAS_INSTAGRAM_ACCOUNT_ID,
    LINAS_PAGE_ID,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaOAuthStateError,
    get_meta_app_configs,
    get_meta_registry_readiness,
)
from services.meta_multi_app_router import resolve_registry_events
from services.social_contact_routing import resolve_social_whatsapp_number
from tests.meta_app_registry_helpers import ALL_MESSAGING_SCOPES, _credential, _page_payload

pytest_plugins = ("tests.meta_app_registry_fixtures",)


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
            credential=_credential(app_a_id, LINAS_PAGE_ID, scopes=ALL_MESSAGING_SCOPES + ("ads_management",)),
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


@pytest.mark.asyncio
async def test_app_b_signature_cannot_route_app_a_active_binding(registry: MetaAppRegistry) -> None:
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
    assert await resolve_registry_events(payload, app_config=configs[APP_B_KEY], registry=registry) == []
    routed = await resolve_registry_events(payload, app_config=configs[APP_A_KEY], registry=registry)
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


def test_authorize_oauth_asset_preserves_comment_webhook_fields_on_reauth(
    registry: MetaAppRegistry,
) -> None:
    """Safe reauth must not wipe feed/comments fields already recorded on the binding."""

    configs = get_meta_app_configs()
    app_a_id = configs[APP_A_KEY].app_id
    first = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
        webhook_subscription_status="active",
        webhook_subscription_checked_at=123.0,
    )
    assert "feed" in first.webhook_subscribed_fields
    refreshed = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=LINAS_PAGE_ID,
        page_id=LINAS_PAGE_ID,
        instagram_account_id=LINAS_INSTAGRAM_ACCOUNT_ID,
        app_key=APP_A_KEY,
        credential=_credential(app_a_id, LINAS_PAGE_ID),
        actor_id="owner-reauth",
        # Defaults would previously wipe feed — must preserve.
    )
    assert refreshed.binding_id == first.binding_id
    assert "feed" in refreshed.webhook_subscribed_fields
    assert "messages" in refreshed.webhook_subscribed_fields
    assert refreshed.webhook_subscription_status == "active"


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
