"""Meta connection lifecycle: disconnect archives credentials; connect uses fresh OAuth."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.requests import Request

from modules import meta_connections_api
from services.dashboard_session_service import SessionRecord
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
    MetaCredentialError,
)
from services.meta_oauth import begin_meta_business_login, complete_meta_business_login

SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "pages_read_user_content",
    "pages_manage_engagement",
    "business_management",
)


def _request(tenant_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/meta/connections",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.dashboard_session = SessionRecord(
        session_id="session-a",
        user_id="owner-a",
        email="owner@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    return request


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID", "facebook-only-config-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_OAUTH_REDIRECT_URI", "https://www.linasaibot.com/oauth/meta/callback")
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="lifecycle-registry-secret-tests-1234567890",
    )


def _active_facebook_binding(registry: MetaAppRegistry, *, token: str = "old-page-token") -> Any:
    page_id = "445566778899"
    return registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=SCOPES,
            expires_at=int(time.time()) + 3600,
            authorized_meta_user_id="112233445566",
        ),
        actor_id="owner",
    )


@pytest.mark.asyncio
async def test_disconnect_archives_credential_and_clears_webhooks(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    binding = _active_facebook_binding(registry)
    unsubscribed = False

    async def unsubscribe(*_args: Any, **_kwargs: Any) -> None:
        nonlocal unsubscribed
        unsubscribed = True

    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("modules.meta_connections_api_helpers.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("modules.meta_connections_api_lifecycle.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(graph, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(graph, "unsubscribe_binding_webhook", unsubscribe)

    async def clear_toggles(**_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(
        "services.channel_capability_disconnect.clear_channel_toggles_after_disconnect",
        clear_toggles,
    )

    response = await meta_connections_api.disconnect_meta_connection(binding.binding_id, _request("tenant-a"))

    assert response["success"] is True
    assert response["connection"]["status"] == "disconnected"
    assert unsubscribed is True
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.status == "disconnected"
    assert refreshed.webhook_subscribed_fields == ()
    with pytest.raises(MetaCredentialError):
        registry.get_credential(refreshed)


@pytest.mark.asyncio
async def test_disconnect_then_oauth_connect_uses_new_credential(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def noop_subscribe(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        noop_subscribe,
    )
    binding = _active_facebook_binding(registry, token="old-page-token-private")
    archived = registry.archive_binding_credential(
        binding.binding_id,
        actor_id="owner",
        expected_generation=binding.generation,
    )
    registry.set_binding_status(
        archived.binding_id,
        status="disconnected",
        actor_id="owner",
        expected_generation=archived.generation,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "integration-token-private"})
        if path.endswith("/debug_token"):
            inspected = request.url.params.get("input_token")
            data: dict[str, Any] = {
                "is_valid": True,
                "app_id": "2963733803971681",
                "scopes": list(SCOPES),
                "expires_at": 4102444800,
                "user_id": "112233445566",
            }
            if inspected == "page-token-private":
                data["profile_id"] = "445566778899"
                data["type"] = "PAGE"
                data["granular_scopes"] = [
                    {"scope": "pages_messaging", "target_ids": ["445566778899"]},
                ]
            return httpx.Response(200, json={"data": data})
        if path.endswith("/me/accounts"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "445566778899",
                            "name": "Clinic Page",
                            "access_token": "page-token-private",
                            "tasks": ["MANAGE", "MESSAGING"],
                        }
                    ]
                },
            )
        if path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    url = begin_meta_business_login(tenant_id="tenant-a", channel="facebook", actor_id="owner", registry=registry)
    nonce = parse_qs(urlparse(url).query)["state"][0]
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0",
        transport=transport,
    ) as client:
        result = await complete_meta_business_login(
            code="oauth-code",
            state=nonce,
            registry=registry,
            client=client,
        )

    assert result.binding.status == "active"
    credential = registry.get_credential(result.binding)
    assert credential.access_token == "page-token-private"
    assert credential.access_token != "old-page-token-private"
    assert set(credential.scopes) >= {"pages_read_user_content", "pages_manage_engagement"}
