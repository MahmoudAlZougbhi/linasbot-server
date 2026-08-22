"""Tests for App-level Meta page webhook subscription helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.meta_app_webhook_subscription import ensure_app_page_webhook_subscription
from services.meta_oauth import MetaOAuthError


@pytest.mark.asyncio
async def test_ensure_app_page_webhook_subscription_posts_include_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "v" * 32)
    response = MagicMock()
    response.json.return_value = {"success": True}
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    app = type("App", (), {"app_id": "app_1", "app_secret": "secret", "graph_api_version": "v24.0"})()

    with patch("services.meta_app_webhook_subscription.get_meta_app_configs", return_value={"linas_first_party": app}):
        await ensure_app_page_webhook_subscription(client=client)

    kwargs = client.post.await_args.kwargs
    assert kwargs["data"]["include_values"] == "true"
    assert "feed" in kwargs["data"]["fields"]


@pytest.mark.asyncio
async def test_ensure_app_page_webhook_subscription_rejects_missing_verify_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("META_WEBHOOK_VERIFY_TOKEN", raising=False)
    with pytest.raises(MetaOAuthError):
        await ensure_app_page_webhook_subscription()
