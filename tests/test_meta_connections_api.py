"""Tenant isolation and secret-free Meta connection control-plane tests."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request

from modules import meta_connections_api
from services.dashboard_session_service import SessionRecord
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaBindingCredential,
)

SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


def _request(tenant_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
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
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-tests")
    monkeypatch.setenv("META_APP_B_LOGIN_CONFIG_ID", "config-b-tests")
    current = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="connection-api-registry-secret-tests-123456789",
    )
    for tenant, page in (("tenant-a", "111222333"), ("tenant-b", "444555666")):
        current.activate_binding(
            tenant_id=tenant,
            channel="facebook",
            asset_id=page,
            page_id=page,
            instagram_account_id="",
            app_key=APP_B_KEY,
            credential=MetaBindingCredential(
                access_token=f"private-token-{tenant}",
                token_app_id="998877665544",
                token_profile_id=page,
                scopes=SCOPES,
                expires_at=int(time.time()) + 3600,
            ),
            actor_id="owner",
            status="testing",
        )
    return current


@pytest.mark.asyncio
async def test_connection_status_is_tenant_isolated_and_secret_free(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meta_connections_api, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)

    response = await meta_connections_api.list_meta_connections(_request("tenant-a"))
    assert response["success"] is True
    assert len(response["connections"]) == 1
    assert response["connections"][0]["tenant_id"] == "tenant-a"
    rendered = json.dumps(response)
    assert "tenant-b" not in rendered
    assert "private-token" not in rendered
    assert "app-a-secret" not in rendered
    assert "app-b-secret" not in rendered


@pytest.mark.asyncio
async def test_connect_start_derives_tenant_from_session_not_request_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def begin(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "https://www.facebook.com/v24.0/dialog/oauth?state=opaque"

    monkeypatch.setattr(meta_connections_api, "begin_meta_business_login", begin)
    response = await meta_connections_api.start_meta_connection(
        _request("tenant-a"),
        {"channel": "instagram", "tenant_id": "tenant-b", "app_id": "untrusted"},
    )
    assert response["success"] is True
    assert captured["tenant_id"] == "tenant-a"
    assert captured["channel"] == "unified"
    assert "app_id" not in captured


@pytest.mark.asyncio
async def test_connect_start_defaults_to_unified_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def begin(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "https://www.facebook.com/v24.0/dialog/oauth?state=opaque"

    monkeypatch.setattr(meta_connections_api, "begin_meta_business_login", begin)
    response = await meta_connections_api.start_meta_connection(_request("tenant-a"), {})
    assert response["success"] is True
    assert captured["channel"] == "unified"


@pytest.mark.asyncio
async def test_authorization_title_is_returned_for_app_a(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry-title.json",
        audit_path=tmp_path / "audit-title.jsonl",
        master_secret="connection-api-title-secret-tests-123456789",
    )
    registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id="111222333",
        page_id="111222333",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="private-token-a",
            token_app_id="2963733803971681",
            token_profile_id="111222333",
            scopes=SCOPES,
            expires_at=int(time.time()) + 3600,
            authorized_meta_user_id="123456789",
        ),
        actor_id="owner",
        page_name="Clinic Page",
        status="active",
    )
    monkeypatch.setattr(meta_connections_api, "meta_multi_app_registry_enabled", lambda: True)
    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)

    response = await meta_connections_api.list_meta_connections(_request("tenant-a"))
    assert response["authorizations"][0]["authorization_title"] == "Meta authorization — App A"
    assert "unknown" not in json.dumps(response["authorizations"])


@pytest.mark.asyncio
async def test_lina_app_b_activation_is_rejected_before_any_subscription(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.delenv("META_APP_B_LINAS_CUTOVER_APPROVED", raising=False)
    binding = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id="378696005334409",
        page_id="378696005334409",
        instagram_account_id="17841413184256533",
        app_key=APP_B_KEY,
        credential=MetaBindingCredential(
            access_token="private-lina-demo-token",
            token_app_id="998877665544",
            token_profile_id="378696005334409",
            scopes=SCOPES,
        ),
        actor_id="review-demo",
        status="testing",
    )
    subscribed = False

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        nonlocal subscribed
        subscribed = True

    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(meta_connections_api, "subscribe_binding_webhook", subscribe)
    with pytest.raises(HTTPException) as blocked:
        await meta_connections_api.activate_meta_connection(binding.binding_id, _request("linas"))
    assert blocked.value.status_code == 409
    assert isinstance(blocked.value.__cause__, MetaBindingConflictError)
    assert subscribed is False


@pytest.mark.asyncio
async def test_reconnect_atomically_replaces_provider_then_removes_old_subscription(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.cm import constants as cm_constants
    from services.cm import version_store

    page_id = "111222333"
    old = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="private-old-provider-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=SCOPES,
            expires_at=int(time.time()) + 3600,
        ),
        actor_id="owner",
    )
    staged = next(
        item for item in registry.list_bindings() if item.tenant_id == "tenant-a" and item.app_key == APP_B_KEY
    )
    calls: list[tuple[str, str]] = []

    async def subscribe(binding: Any, **_kwargs: Any) -> None:
        calls.append(("subscribe", binding.app_key))

    async def unsubscribe(binding: Any, **_kwargs: Any) -> None:
        calls.append(("unsubscribe", binding.app_key))

    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(meta_connections_api, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_connections_api, "unsubscribe_binding_webhook", unsubscribe)
    monkeypatch.setattr(cm_constants, "cm_runtime_mode", lambda: "published")
    monkeypatch.setattr(version_store, "load_published_content", lambda _tenant: ({}, {}))

    response = await meta_connections_api.activate_meta_connection(
        staged.binding_id,
        _request("tenant-a"),
    )

    assert response["success"] is True
    assert response["connection"]["app_key"] == APP_B_KEY
    assert registry.get_active_bindings_for_app(APP_A_KEY) == []
    assert [item.binding_id for item in registry.get_active_bindings_for_app(APP_B_KEY)] == [staged.binding_id]
    assert calls == [("subscribe", APP_B_KEY), ("unsubscribe", APP_A_KEY)]
    inactive_old = next(item for item in registry.list_bindings() if item.binding_id == old.binding_id)
    assert inactive_old.status == "inactive"


@pytest.mark.asyncio
async def test_reconnect_first_party_disconnected_binding(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_id = "378696005334409"
    binding = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="private-lina-page-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=SCOPES,
            expires_at=int(time.time()) + 3600,
        ),
        actor_id="owner",
    )
    disconnected = registry.set_binding_status(
        binding.binding_id,
        status="disconnected",
        actor_id="owner",
    )
    subscribed = False

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        nonlocal subscribed
        subscribed = True

    monkeypatch.setattr(meta_connections_api, "get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(meta_connections_api, "subscribe_binding_webhook", subscribe)

    response = await meta_connections_api.reconnect_meta_connection(
        disconnected.binding_id,
        _request("linas"),
    )

    assert response["success"] is True
    assert response["connection"]["status"] == "active"
    assert subscribed is True
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.status == "active"
