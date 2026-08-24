"""Regression: permission hardening must not break DM or Facebook comment paths."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.channel_capability_state import comment_capability_state, dm_capability_state
from services.cm.actions import comments_enforcement_decision
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_comment_permission_verification import bootstrap_unknown_comment_permissions
from tests.meta_instagram_login_lifecycle_helpers import _binding


@pytest.fixture
def meta_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "comment-regression-secret-123456789012345")


@pytest.fixture
def registry(tmp_path: Path, meta_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="comment-regression-secret-123456789012345",
    )


def _facebook_page_binding(registry: MetaAppRegistry):
    return registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id="page-378696",
        page_id="page-378696",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="facebook-page-token",
            token_app_id="2963733803971681",
            token_profile_id="page-378696",
            scopes=(
                "pages_messaging",
                "pages_read_user_content",
                "pages_manage_engagement",
                "pages_read_engagement",
            ),
            expires_at=int(time.time()) + 3600,
            authorized_meta_user_id="meta-user",
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        page_name="Linas Page",
        status="active",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
    )


def test_pre_lb_backfill_keeps_facebook_comments_granted(registry: MetaAppRegistry) -> None:
    binding = _facebook_page_binding(registry)
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id="",
        comment_permission_token_fingerprint="",
        actor_id="test_reset",
    )
    result = bootstrap_unknown_comment_permissions(registry=registry, actor_id="pre_lb_backfill")
    assert result["updated"] >= 1
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.comment_permission_status == "verified_granted"
    assert refreshed.comment_permission_source == "migration_stored_scopes"


def test_backfill_leaves_no_unknown_active_bindings_when_scopes_present(registry: MetaAppRegistry) -> None:
    from services.meta_comment_permission_verification import (
        bootstrap_unknown_comment_permissions,
        count_active_bindings_with_unknown_comment_permission,
    )

    _facebook_page_binding(registry)
    bootstrap_unknown_comment_permissions(registry=registry, actor_id="pre_lb_backfill")
    assert count_active_bindings_with_unknown_comment_permission(registry=registry) == 0


def test_facebook_comments_enforcement_still_allows_after_backfill(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("services.cm.constants.tenant_uses_cm_runtime", lambda _tenant: True)
    monkeypatch.setattr(
        "services.cm.actions.comments_action_enabled",
        lambda _tenant, channel: channel == "facebook",
    )
    binding = _facebook_page_binding(registry)
    credential = registry.get_credential(binding)
    decision = comments_enforcement_decision(
        tenant_id="linas",
        channel="facebook",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    assert decision["allow"] is True
    assert decision["permission"]["status"] == "verified_granted"


def test_facebook_comments_capability_not_unknown_after_backfill(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facebook_page_binding(registry)
    monkeypatch.setattr("services.channel_capability_state.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.channel_capability_state._action_requested", lambda *_a, **_k: True)
    monkeypatch.setattr("services.channel_capability_state._tenant_comment_assets_enabled", lambda *_a, **_k: True)
    bootstrap_unknown_comment_permissions(registry=registry)
    state = comment_capability_state("linas", "facebook")
    assert "unknown" not in state.get("comment_permission_statuses", [])
    assert state["blocker_code"] != "comment_permissions_could_not_be_verified"


def test_instagram_dm_capability_unchanged_by_comment_permission_columns(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    monkeypatch.setattr("services.channel_capability_state.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.channel_capability_state._action_requested", lambda *_a, **_k: True)
    state = dm_capability_state("tenant-a", "instagram")
    assert state["blocker_code"] != "comment_permissions_could_not_be_verified"
    assert state["connection_healthy"] is True


def test_facebook_dm_capability_unchanged(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facebook_page_binding(registry)
    monkeypatch.setattr("services.channel_capability_state.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.channel_capability_state._action_requested", lambda *_a, **_k: True)
    state = dm_capability_state("linas", "facebook")
    assert state["blocker_code"] != "comment_permissions_could_not_be_verified"
    assert state["connection_healthy"] is True


def test_legacy_simple_namespace_comment_capability_still_works() -> None:
    binding = SimpleNamespace(
        tenant_id="linas",
        channel="facebook",
        status="active",
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
        asset_id="page1",
        binding_id="b2",
        page_id="page1",
    )
    credential = SimpleNamespace(
        scopes=("pages_read_user_content", "pages_manage_engagement", "pages_messaging"),
    )
    registry = SimpleNamespace(get_credential=lambda _binding: credential)
    with (
        patch("services.channel_capability_state.get_meta_app_registry", lambda: registry),
        patch(
            "services.channel_capability_state.canonical_channel_bindings",
            lambda *_a, **_k: [binding],
        ),
        patch(
            "services.channel_capability_state._action_requested",
            lambda *_a, **_k: True,
        ),
        patch(
            "services.channel_capability_state._tenant_comment_assets_enabled",
            lambda *_a, **_k: True,
        ),
        patch(
            "services.channel_capability_state._binding_connection_healthy",
            lambda *_a, **_k: True,
        ),
    ):
        state = comment_capability_state("linas", "facebook")
    assert state["blocker_code"] != "comment_permissions_could_not_be_verified"
    assert state["permission_present"] is True
