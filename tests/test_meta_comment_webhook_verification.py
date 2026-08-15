"""Meta comment webhook enablement must verify provider state before local readiness."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
from services.meta_comment_webhooks import (
    ensure_instagram_comment_app_webhook,
    ensure_page_comment_webhook_subscription,
)
from services.meta_oauth import MetaOAuthError


def _facebook_binding() -> MetaAssetBinding:
    return MetaAssetBinding(
        binding_id="binding-fb",
        tenant_id="linas",
        channel="facebook",
        asset_id="378696005334409",
        page_id="378696005334409",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential_id="credential-fb",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
        auth_flow="facebook_login",
    )


def _patch_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    app = SimpleNamespace(
        app_id="2963733803971681",
        app_secret="app-secret",
        verify_token="verify-token",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr("services.meta_comment_webhooks.get_meta_app_configs", lambda: {APP_A_KEY: app})
    return app


def _registry(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        _backend="file",
        lock_path=tmp_path / "registry.lock",
        get_credential=lambda _binding: SimpleNamespace(access_token="page-token"),
    )


@pytest.mark.asyncio
async def test_page_comment_subscription_requires_success_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_app(monkeypatch)
    registry = _registry(tmp_path)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(MetaOAuthError, match="did not confirm"):
            await ensure_page_comment_webhook_subscription(
                _facebook_binding(),
                registry=registry,
                client=client,
            )


@pytest.mark.asyncio
async def test_page_comment_subscription_get_verifies_feed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _patch_app(monkeypatch)
    registry = _registry(tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": app.app_id,
                        "subscribed_fields": ["feed", "messages", "messaging_postbacks"],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0",
        transport=httpx.MockTransport(handler),
    ) as client:
        await ensure_page_comment_webhook_subscription(
            _facebook_binding(),
            registry=registry,
            client=client,
        )


@pytest.mark.asyncio
async def test_page_comment_subscription_rejects_unverified_feed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _patch_app(monkeypatch)
    registry = _registry(tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={"data": [{"id": app.app_id, "subscribed_fields": ["messages", "messaging_postbacks"]}]},
        )

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(MetaOAuthError, match="could not be verified"):
            await ensure_page_comment_webhook_subscription(
                _facebook_binding(),
                registry=registry,
                client=client,
            )


@pytest.mark.asyncio
async def test_legacy_instagram_comment_subscription_fails_before_any_graph_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_app(monkeypatch)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(
        base_url="https://graph.facebook.com/v24.0",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(MetaOAuthError, match="reconnect via Instagram Login"):
            await ensure_instagram_comment_app_webhook(app_key=APP_A_KEY, client=client)

    assert requests == []
