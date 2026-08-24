"""Production-safe Meta comment permission verification tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.cm.actions import comments_enforcement_decision, evaluate_comments_meta_readiness
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
)
from services.meta_comment_permission_verification import (
    comment_permission_token_fingerprint,
    effective_comment_permission_status,
    maybe_reconcile_binding_comment_permission,
    persist_comment_permission_from_credential,
    reconcile_binding_comment_permission,
    verification_matches_current_credential,
)
from services.meta_comment_reply_settings import set_comment_reply_setting
from tests.meta_instagram_login_lifecycle_helpers import FULL_SCOPES, INSTAGRAM_ID, PAGE_SCOPES, _binding


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "comment-perm-tests-secret-123456789012345")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="comment-perm-tests-secret-123456789012345",
    )


def _enable_cm_comments(monkeypatch: pytest.MonkeyPatch, tenant_id: str = "tenant-a") -> None:
    monkeypatch.setattr(
        "services.cm.actions.comments_action_enabled",
        lambda _tenant, channel: channel in {"instagram", "facebook"},
    )
    monkeypatch.setattr(
        "services.cm.constants.tenant_uses_cm_runtime",
        lambda _tenant: True,
    )


def test_granted_allows_reply(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_cm_comments(monkeypatch)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    assert effective_comment_permission_status(binding, credential) == "verified_granted"
    decision = comments_enforcement_decision(
        tenant_id="tenant-a",
        channel="instagram",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    assert decision["allow"] is True
    assert decision["reason"] == "ok"


def test_explicitly_missing_denies_with_clear_reason(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_cm_comments(monkeypatch)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES[:2],
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    assert effective_comment_permission_status(binding, credential) == "verified_missing"
    decision = comments_enforcement_decision(
        tenant_id="tenant-a",
        channel="instagram",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    assert decision["allow"] is False
    assert decision["reason"] == "comment_scopes_missing"


def test_unknown_with_stored_scopes_is_verified_at_runtime(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_cm_comments(monkeypatch)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id="",
        comment_permission_token_fingerprint="",
        actor_id="test",
    )
    decision = comments_enforcement_decision(
        tenant_id="tenant-a",
        channel="instagram",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    assert decision["allow"] is True
    assert decision["permission"]["status"] == "verified_granted"


def test_unknown_without_stored_scopes_and_no_verification_blocks(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_cm_comments(monkeypatch)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES[:2],
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id=binding.credential_id,
        comment_permission_token_fingerprint=comment_permission_token_fingerprint(credential.access_token),
        actor_id="test",
    )
    with patch(
        "services.meta_comment_permission_verification.persist_comment_permission_from_credential",
        side_effect=RuntimeError("no stored scopes path"),
    ):
        decision = comments_enforcement_decision(
            tenant_id="tenant-a",
            channel="instagram",
            per_asset_enabled=True,
            binding=binding,
            credential=credential,
            registry=registry,
        )
    assert decision["allow"] is False
    assert decision["reason"] == "comment_permissions_could_not_be_verified"


@pytest.mark.asyncio
async def test_transient_meta_failure_keeps_last_known_good(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="verified_granted",
        comment_permission_verified_at=time.time(),
        comment_permission_source="debug_token",
        comment_permission_credential_id=binding.credential_id,
        comment_permission_token_fingerprint=comment_permission_token_fingerprint(credential.access_token),
        actor_id="test",
    )
    with patch(
        "services.meta_comment_permission_verification._debug_token",
        new=AsyncMock(side_effect=httpx.HTTPError("network")),
    ):
        updated = await reconcile_binding_comment_permission(binding, registry=registry)
    assert updated.comment_permission_status == "verified_granted"


def test_token_rotation_invalidates_old_verification(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    assert effective_comment_permission_status(binding, credential) == "verified_granted"
    rotated = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="rotated-token",
            token_app_id="1035856539045307",
            token_profile_id=INSTAGRAM_ID,
            scopes=FULL_SCOPES,
            expires_at=int(time.time()) + 3600,
            authorized_meta_user_id="998877",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        status="active",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
    )
    new_credential = registry.get_credential(rotated)
    assert verification_matches_current_credential(rotated, new_credential) is True
    from dataclasses import replace

    stale = replace(
        rotated,
        comment_permission_token_fingerprint=comment_permission_token_fingerprint(credential.access_token),
    )
    assert verification_matches_current_credential(stale, new_credential) is False


def test_instagram_login_readiness_uses_business_manage_comments(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    readiness = evaluate_comments_meta_readiness(
        channel="instagram",
        cm_action_enabled=True,
        per_asset_switch_enabled=True,
        binding=binding,
        credential=credential,
    )
    assert readiness["scopes_required"] == ["instagram_business_manage_comments"]
    assert readiness["scopes_ready"] is True


def test_facebook_login_instagram_readiness_uses_manage_comments(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="facebook_login",
        scopes=PAGE_SCOPES,
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    readiness = evaluate_comments_meta_readiness(
        channel="instagram",
        cm_action_enabled=True,
        per_asset_switch_enabled=True,
        binding=binding,
        credential=credential,
    )
    assert readiness["scopes_required"] == ["instagram_manage_comments"]
    assert readiness["scopes_ready"] is True


def test_webhook_and_polling_share_enforcement_decision(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.meta_social_comment_sync import _comment_reply_enabled

    _enable_cm_comments(monkeypatch)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id="",
        comment_permission_token_fingerprint="",
        actor_id="test",
    )
    set_comment_reply_setting(
        tenant_id="tenant-a",
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
        enabled=True,
    )
    credential = registry.get_credential(binding)
    webhook_decision = comments_enforcement_decision(
        tenant_id="tenant-a",
        channel="instagram",
        per_asset_enabled=True,
        binding=binding,
        credential=credential,
        registry=registry,
    )
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    polling_enabled = _comment_reply_enabled(binding)
    assert webhook_decision["allow"] is True
    assert polling_enabled is True


def test_toggle_stays_on_with_blocker_when_unknown(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.channel_capability_state import comment_capability_state
    from services.meta_comment_reply_settings import set_comment_reply_setting

    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    set_comment_reply_setting(
        tenant_id="tenant-a",
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
        enabled=True,
    )
    registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id="",
        comment_permission_token_fingerprint="",
        actor_id="test",
    )
    monkeypatch.setattr("services.channel_capability_state.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    state = comment_capability_state("tenant-a", "instagram")
    assert state["tenant_action_enabled"] is True
    assert state["blocker_code"] == "comment_permissions_could_not_be_verified"


def test_reconcile_scheduled_for_unknown_binding(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    binding = registry.update_comment_permission_verification(
        binding.binding_id,
        comment_permission_status="unknown",
        comment_permission_verified_at=0,
        comment_permission_source="",
        comment_permission_credential_id="",
        comment_permission_token_fingerprint="",
        actor_id="test",
    )
    assert maybe_reconcile_binding_comment_permission(binding, registry=registry) is True


def test_persist_from_credential_sets_postgres_backed_state(registry: MetaAppRegistry) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        webhook_fields=("messages", "messaging_postbacks", "comments"),
    )
    credential = registry.get_credential(binding)
    updated = persist_comment_permission_from_credential(binding, credential, registry=registry)
    assert updated.comment_permission_status == "verified_granted"
    assert updated.comment_permission_source == "oauth_stored_scopes"
    assert updated.comment_permission_credential_id == binding.credential_id
