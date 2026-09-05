"""Meta password/session invalidation disconnects the binding for every tenant."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_app_registry_session import PASSWORD_CHANGED_RECONNECT
from services.meta_session_invalidated import (
    is_meta_session_invalidated,
    latest_password_changed_binding,
    mark_if_session_invalidated,
    probe_binding_session,
)
from services.mobile_integrations_display import enrich_mobile_integration_row
from services.omnichannel.meta_errors import MetaProviderError
from tests.meta_app_registry_helpers import _credential

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
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-token-registry-secret-tests-1234567890",
    )


def _instagram_binding(registry: MetaAppRegistry, *, tenant_id: str = "clinic-a") -> object:
    return registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="live-ig-token",
            token_app_id="1035856539045307",
            token_profile_id=INSTAGRAM_ID,
            scopes=("instagram_business_basic", "instagram_business_manage_messages"),
            expires_at=int(time.time()) + 86_400,
            authorized_meta_user_id="998877",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
    )


def test_detects_graph_190_and_password_change_wording() -> None:
    assert is_meta_session_invalidated(error_code=190)
    assert is_meta_session_invalidated(
        MetaProviderError("Meta Send API returned HTTP 401 code=190", http_status=401, error_code=190)
    )
    assert is_meta_session_invalidated(
        error_text="The session has been invalidated because the user changed their password"
    )
    assert not is_meta_session_invalidated(http_status=401, error_code=10)
    assert not is_meta_session_invalidated(RuntimeError("timeout"))


def test_mark_disconnects_active_binding_for_any_tenant(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry, tenant_id="acme-clinic")
    assert binding.status == "active"

    marked = mark_if_session_invalidated(
        MetaProviderError("HTTP 401 code=190", http_status=401, error_code=190),
        binding_id=binding.binding_id,
        registry=registry,
    )
    assert marked is True

    latest = next(
        item for item in registry.list_bindings(include_inactive=True) if item.binding_id == binding.binding_id
    )
    assert latest.status == "disconnected"
    assert latest.webhook_subscription_error == PASSWORD_CHANGED_RECONNECT
    assert latest.generation == binding.generation + 1

    again = mark_if_session_invalidated(
        error_code=190,
        binding_id=binding.binding_id,
        registry=registry,
    )
    assert again is True
    same = next(item for item in registry.list_bindings(include_inactive=True) if item.binding_id == binding.binding_id)
    assert same.generation == latest.generation


def test_mark_ignores_non_session_errors(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry)
    assert (
        mark_if_session_invalidated(
            MetaProviderError("HTTP 400 code=100", http_status=400, error_code=100),
            binding_id=binding.binding_id,
            registry=registry,
        )
        is False
    )
    latest = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert latest.status == "active"


@pytest.mark.asyncio
async def test_probe_marks_binding_on_graph_me_190(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry, tenant_id="linas")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "live-ig-token" not in str(request.url)
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "The session has been invalidated because the user changed their password",
                    "type": "OAuthException",
                    "code": 190,
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    marked = await probe_binding_session(binding, registry=registry, client=client)
    assert marked is True
    latest = next(
        item for item in registry.list_bindings(include_inactive=True) if item.binding_id == binding.binding_id
    )
    assert latest.status == "disconnected"
    assert latest.webhook_subscription_error == PASSWORD_CHANGED_RECONNECT


@pytest.mark.asyncio
async def test_probe_leaves_binding_when_graph_me_ok(registry: MetaAppRegistry) -> None:
    binding = _instagram_binding(registry)

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"id": INSTAGRAM_ID})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    marked = await probe_binding_session(binding, registry=registry, client=client)
    assert marked is False
    latest = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert latest.status == "active"


def test_display_shows_needs_reconnect_after_password_change(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _instagram_binding(registry, tenant_id="linas")
    registry.mark_binding_session_invalidated(binding.binding_id)
    monkeypatch.setattr(
        "services.mobile_integrations_display.canonical_channel_bindings",
        lambda tenant_id, platform: [],
    )
    monkeypatch.setattr("services.mobile_integrations_display.get_meta_app_registry", lambda: registry)

    enriched = enrich_mobile_integration_row(
        {
            "platform": "instagram",
            "label": "Instagram",
            "connected": False,
            "toggles": {"dm": True, "comments": False},
        },
        tenant_id="linas",
    )
    assert enriched["connection_status"] == "needs_reconnect"
    assert enriched["service_diagnostic"] == PASSWORD_CHANGED_RECONNECT
    assert enriched["account"]["username"] == "clinic_ig"
    found = latest_password_changed_binding("linas", "instagram", registry=registry)
    assert found is not None
    assert found.binding_id == binding.binding_id


def test_facebook_binding_can_be_marked(registry: MetaAppRegistry) -> None:
    app_id = "2963733803971681"
    binding = registry.activate_binding(
        tenant_id="shop-b",
        channel="facebook",
        asset_id="445566778899",
        page_id="445566778899",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(app_id, "445566778899"),
        actor_id="owner",
    )
    assert mark_if_session_invalidated(error_code=190, binding_id=binding.binding_id, registry=registry) is True
    latest = next(
        item for item in registry.list_bindings(include_inactive=True) if item.binding_id == binding.binding_id
    )
    assert latest.status == "disconnected"
    assert latest.webhook_subscription_error == PASSWORD_CHANGED_RECONNECT
