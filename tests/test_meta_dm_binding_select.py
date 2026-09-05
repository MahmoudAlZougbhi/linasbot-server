"""Instagram DM outbound must use Instagram Login when that binding is ready."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.meta_app_registry import MetaAppRegistry
from services.meta_dm_binding_select import select_binding_for_meta_dm
from services.meta_messaging import MetaMessagingAdapter
from services.requests.constants import SOURCE_CHANNEL_INSTAGRAM_DM
from services.requests.delivery import deliver_meta_dm
from tests.test_meta_graph_routing import INSTAGRAM_ID, _instagram_binding


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
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-routing-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-routing-secret-tests-1234567890",
    )


def test_select_binding_prefers_instagram_login(registry: MetaAppRegistry) -> None:
    page = _instagram_binding(registry, auth_flow="facebook_login")
    direct = _instagram_binding(registry, auth_flow="instagram_login", legacy_duplicate=True)
    candidates = list(registry.list_bindings(include_inactive=False))
    assert candidates[0].binding_id == page.binding_id
    selected = select_binding_for_meta_dm(candidates, channel="instagram", registry=registry)
    assert selected is not None
    assert selected.binding_id == direct.binding_id


@pytest.mark.asyncio
async def test_deliver_meta_dm_sends_with_instagram_login_host(
    registry: MetaAppRegistry, instagram_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _instagram_binding(registry, auth_flow="facebook_login")
    _instagram_binding(registry, auth_flow="instagram_login", legacy_duplicate=True)
    captured: dict[str, Any] = {}

    class FakeAdapter:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def send_text_message(self, recipient: str, text: str) -> dict[str, Any]:
            return {"success": True, "data": [{"message_id": "mid-ig-1"}]}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_messaging.MetaMessagingAdapter", FakeAdapter)

    result = await deliver_meta_dm(
        tenant_id="tenant-a",
        source_channel=SOURCE_CHANNEL_INSTAGRAM_DM,
        source_account_id=INSTAGRAM_ID,
        external_customer_id="igsid-tester",
        text="hello from live chat",
    )
    assert result.status == "sent"
    assert captured["graph_base_url"] == "https://graph.instagram.com"
    assert captured["access_token"] == "token-b"


@pytest.mark.asyncio
async def test_instagram_login_send_omits_messaging_type() -> None:
    captured: list[dict[str, Any]] = []

    async def fake_post(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"message_id": "mid-1"}

    adapter = MetaMessagingAdapter(
        access_token="ig-token",
        account_id=INSTAGRAM_ID,
        channel="instagram",
        graph_base_url="https://graph.instagram.com",
    )
    adapter._post = fake_post  # type: ignore[method-assign]
    result = await adapter.send_text_message("igsid-1", "hi")
    assert result["success"] is True
    assert "messaging_type" not in captured[0]


@pytest.mark.asyncio
async def test_facebook_send_keeps_messaging_type() -> None:
    captured: list[dict[str, Any]] = []

    async def fake_post(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"message_id": "mid-fb"}

    adapter = MetaMessagingAdapter(
        access_token="page-token",
        account_id="378696005334409",
        channel="facebook",
        graph_base_url="https://graph.facebook.com",
    )
    adapter._post = fake_post  # type: ignore[method-assign]
    result = await adapter.send_text_message("psid-1", "hi")
    assert result["success"] is True
    assert captured[0]["messaging_type"] == "RESPONSE"
