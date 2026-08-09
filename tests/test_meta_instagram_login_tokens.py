"""Instagram Login token refresh locking tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_instagram_login_config import instagram_login_refresh_lead_seconds
from services.meta_instagram_login_oauth import credential_needs_refresh
from services.meta_instagram_login_tokens import refresh_binding_instagram_login_token
from services.meta_oauth import MetaOAuthError

INSTAGRAM_ID = "17840000999900011"


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
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-token-registry-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-token-registry-secret-tests-1234567890",
    )


@pytest.fixture
def binding(registry: MetaAppRegistry) -> object:
    return registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="expiring-token",
            token_app_id="1035856539045307",
            token_profile_id=INSTAGRAM_ID,
            scopes=("instagram_business_basic", "instagram_business_manage_messages"),
            expires_at=int(time.time()) + instagram_login_refresh_lead_seconds() - 60,
            authorized_meta_user_id="998877",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
    )


@pytest.mark.asyncio
async def test_refresh_binding_returns_existing_credential_when_lock_not_acquired(
    registry: MetaAppRegistry,
    binding: object,
) -> None:
    with patch("services.meta_instagram_login_tokens.try_acquire_job_lock", return_value=False):
        credential = await refresh_binding_instagram_login_token(binding, registry=registry)
    assert credential.access_token == "expiring-token"


@pytest.mark.asyncio
async def test_refresh_binding_replaces_token_atomically(registry: MetaAppRegistry, binding: object) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "refreshed-token", "token_type": "bearer", "expires_in": 5_183_944},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://graph.instagram.com")
    with patch("services.meta_instagram_login_tokens.try_acquire_job_lock", return_value=True):
        credential = await refresh_binding_instagram_login_token(binding, registry=registry, client=client)
    assert credential.access_token == "refreshed-token"
    stored = registry.get_credential(binding)
    assert stored.access_token == "refreshed-token"
    assert "refreshed-token" not in registry.store_path.read_text(encoding="utf-8")


def test_credential_does_not_refresh_before_lead_window() -> None:
    lead = instagram_login_refresh_lead_seconds()
    credential = MetaBindingCredential(
        access_token="fresh-token",
        token_app_id="1035856539045307",
        token_profile_id=INSTAGRAM_ID,
        scopes=("instagram_business_basic", "instagram_business_manage_messages"),
        expires_at=int(time.time()) + lead + 3600,
        authorized_meta_user_id="998877",
        auth_flow="instagram_login",
    )
    assert credential_needs_refresh(credential) is False


@pytest.mark.asyncio
async def test_refresh_disconnects_when_token_expired(registry: MetaAppRegistry, binding: object) -> None:
    expired = registry.set_binding_status(binding.binding_id, status="active", actor_id="test")
    credential = registry.get_credential(expired)
    registry.authorize_oauth_asset(
        tenant_id=expired.tenant_id,
        channel="instagram",
        asset_id=expired.asset_id,
        page_id="",
        instagram_account_id=expired.asset_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=credential.access_token,
            token_app_id=credential.token_app_id,
            token_profile_id=credential.token_profile_id,
            scopes=credential.scopes,
            expires_at=int(time.time()) - 60,
            authorized_meta_user_id=credential.authorized_meta_user_id,
            auth_flow="instagram_login",
        ),
        actor_id="test",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
    )
    with patch("services.meta_instagram_login_tokens.try_acquire_job_lock", return_value=True):
        with pytest.raises(MetaOAuthError, match="reconnect"):
            await refresh_binding_instagram_login_token(binding, registry=registry)
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.status == "disconnected"
