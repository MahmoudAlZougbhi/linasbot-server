"""Shared helpers for Instagram single-active ownership tests."""

from __future__ import annotations

import time
from typing import Any

import pytest
from starlette.requests import Request

from services.dashboard_session_service import SessionRecord
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
)

PAGE_ID = "445566778899"
INSTAGRAM_ID = "17840000999900001"


def _credential(*, token: str, auth_flow: str, profile_id: str) -> MetaBindingCredential:
    scopes = (
        (
            "instagram_business_basic",
            "instagram_business_manage_messages",
            "instagram_business_manage_comments",
        )
        if auth_flow == "instagram_login"
        else (
            "pages_show_list",
            "pages_manage_metadata",
            "pages_read_engagement",
            "pages_messaging",
            "instagram_basic",
            "instagram_manage_messages",
        )
    )
    return MetaBindingCredential(
        access_token=token,
        token_app_id="1035856539045307" if auth_flow == "instagram_login" else "2963733803971681",
        token_profile_id=profile_id,
        scopes=scopes,
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id="9988776655",
        auth_flow=auth_flow,  # type: ignore[arg-type]
    )


def _facebook_and_linked_instagram(registry: MetaAppRegistry) -> tuple[Any, Any]:
    facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="facebook-page-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        page_name="Clinic Page",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
    )
    linked = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="page-linked-ig-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        instagram_username="clinic_linked",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
    )
    return facebook, linked


def _stage_direct_instagram(
    registry: MetaAppRegistry,
    *,
    tenant_id: str = "tenant-a",
    webhook_subscription_status: str = "ready",
    webhook_subscribed_fields: tuple[str, ...] = ("messages", "messaging_postbacks", "comments"),
) -> Any:
    return registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(
            token=f"direct-ig-token-{tenant_id}",
            auth_flow="instagram_login",
            profile_id=INSTAGRAM_ID,
        ),
        actor_id="owner",
        instagram_username="clinic_direct",
        status="testing",
        auth_flow="instagram_login",
        webhook_subscription_status=webhook_subscription_status,
        webhook_subscribed_fields=webhook_subscribed_fields,
        create_new_binding=True,
    )


def _activate_direct(registry: MetaAppRegistry) -> tuple[Any, Any, Any]:
    facebook, linked = _facebook_and_linked_instagram(registry)
    staged = _stage_direct_instagram(registry)
    direct = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
        replace_existing=True,
    )
    registry.archive_superseded_duplicate_bindings(actor_id="owner")
    return facebook, linked, direct


def _force_binding_fields(registry: MetaAppRegistry, binding_id: str, **fields: Any) -> None:
    with registry._locked():
        state = registry._read_unlocked()
        raw = dict(state["bindings"][binding_id])
        raw.update(fields)
        state["bindings"][binding_id] = raw
        registry._write_unlocked(state)


def _request(tenant_id: str = "tenant-a") -> Request:
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


def _patch_route_registry(monkeypatch: pytest.MonkeyPatch, registry: MetaAppRegistry) -> None:
    monkeypatch.setattr("modules.meta_connections_api_helpers.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("modules.meta_connections_api_lifecycle.get_meta_app_registry", lambda: registry)


def _patch_direct_provider_cleanup(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    present = True

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...] | None:
        calls.append("inspect")
        return ("comments", "messages", "messaging_postbacks") if present else None

    async def delete(*_args: Any, **_kwargs: Any) -> None:
        nonlocal present
        calls.append("delete")
        present = False

    monkeypatch.setattr("services.meta_oauth_graph.inspect_instagram_login_webhook_subscription", inspect)
    monkeypatch.setattr("services.meta_oauth_graph.unsubscribe_instagram_login_webhook_raw", delete)
    return calls
