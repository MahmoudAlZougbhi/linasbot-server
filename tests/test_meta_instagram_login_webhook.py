"""Instagram Login webhook routing and signature tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential, get_meta_app_configs
from services.meta_instagram_login_config import (
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    instagram_login_config_status,
    instagram_login_webhook_verify_token,
    verify_instagram_login_challenge_token,
    verify_instagram_login_webhook_signature,
)
from services.meta_multi_app_router import resolve_registry_events

INSTAGRAM_SCOPES = tuple(sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES))


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-webhook-registry-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-webhook-registry-secret-tests-1234567890",
    )


def test_instagram_login_webhook_verify_token_requires_dedicated_secret(instagram_env: None) -> None:
    assert instagram_login_webhook_verify_token() == "verify-ig-login-tests"
    assert verify_instagram_login_challenge_token("verify-ig-login-tests")
    assert not verify_instagram_login_challenge_token("verify-a-tests")


def test_instagram_login_webhook_signature_uses_instagram_secret_only(instagram_env: None) -> None:
    body = b'{"object":"instagram"}'
    instagram_digest = hmac.new(b"instagram-app-secret-tests", body, hashlib.sha256).hexdigest()
    app_a_digest = hmac.new(b"app-a-secret-tests", body, hashlib.sha256).hexdigest()
    assert verify_instagram_login_webhook_signature(body, f"sha256={instagram_digest}")
    assert not verify_instagram_login_webhook_signature(body, f"sha256={app_a_digest}")
    assert not verify_instagram_login_webhook_signature(body, None)


def test_instagram_login_config_status_reports_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.delenv("META_INSTAGRAM_LOGIN_APP_SECRET", raising=False)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    status = instagram_login_config_status()
    assert not status.configured
    assert "META_INSTAGRAM_LOGIN_APP_SECRET" in status.missing


@pytest.mark.asyncio
async def test_resolve_registry_events_filters_instagram_login_bindings(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900001"
    registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="ig-login-token",
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=INSTAGRAM_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": instagram_id},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-1", "text": "hello"},
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    instagram_routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    facebook_routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="facebook_login",
    )
    assert len(instagram_routed) == 1
    assert instagram_routed[0].binding.auth_flow == "instagram_login"
    assert instagram_routed[0].settings.graph_base_url == "https://graph.instagram.com"
    assert instagram_routed[0].settings.app_secret == "instagram-app-secret-tests"
    assert facebook_routed == []
    assert "ig-login-token" not in json.dumps(instagram_routed[0].event)


def _authorize_instagram_login_binding(
    registry: MetaAppRegistry,
    *,
    tenant_id: str,
    instagram_id: str,
    token: str = "ig-login-token",
) -> None:
    registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=INSTAGRAM_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )


@pytest.mark.asyncio
async def test_resolve_registry_events_isolates_cross_tenant_bindings(registry: MetaAppRegistry) -> None:
    tenant_a_ig = "17840000999900001"
    tenant_b_ig = "17840000999900099"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=tenant_a_ig)
    _authorize_instagram_login_binding(registry, tenant_id="tenant-b", instagram_id=tenant_b_ig, token="other-token")
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": tenant_a_ig,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": tenant_a_ig},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-tenant", "text": "hello"},
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    routed = await resolve_registry_events(
        payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(routed) == 1
    assert routed[0].settings.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_resolve_registry_events_parses_postback_and_comment_fixtures(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900002"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=instagram_id)
    postback_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-2"},
                        "recipient": {"id": instagram_id},
                        "timestamp": 1_700_000_001_000,
                        "postback": {"mid": "pb-1", "title": "Book", "payload": "BOOK_NOW"},
                    }
                ],
            }
        ],
    }
    comment_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-1",
                            "from": {"id": "commenter-1"},
                            "text": "price?",
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }
    app_config = get_meta_app_configs()[APP_A_KEY]
    postback_routed = await resolve_registry_events(
        postback_payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(postback_routed) == 1
    assert postback_routed[0].event.get("is_postback") is True

    comment_routed = await resolve_registry_events(
        comment_payload,
        app_config=app_config,
        registry=registry,
        auth_flow="instagram_login",
    )
    assert comment_routed == []


@pytest.mark.asyncio
async def test_resolve_registry_events_skips_echo_messages(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900003"
    _authorize_instagram_login_binding(registry, tenant_id="tenant-a", instagram_id=instagram_id)
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": instagram_id},
                        "recipient": {"id": "sender-3"},
                        "timestamp": 1_700_000_002_000,
                        "message": {"mid": "echo-1", "text": "bot reply", "is_echo": True},
                    }
                ],
            }
        ],
    }
    routed = await resolve_registry_events(
        payload,
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="instagram_login",
    )
    assert routed == []
