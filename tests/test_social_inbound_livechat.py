"""Instagram/FB inbound must leave a Live Chat row when Terra is skipped."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

import config
from services.integrations.meta.meta_messaging import MetaMessagingSettings
from services.integrations.social import social_messaging_processor
from services.integrations.social.social_inbound_livechat import (
    hashed_message_id,
    persist_skipped_social_inbound,
)


def _settings() -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="page-1",
        page_access_token="token",
        instagram_account_id="ig-asset-1",
        verify_token="verify",
        graph_api_version="v24.0",
        tenant_id="tenant-a",
        binding_id="bind-ig-1",
    )


def _event(**overrides: Any) -> dict[str, Any]:
    payload = {
        "channel": "instagram",
        "sender_id": "igsid-tester",
        "recipient_id": "ig-asset-1",
        "account_id": "ig-asset-1",
        "message_id": "mid-ig-silent-1",
        "text": "مرحبا",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_dm_disabled_persists_livechat_and_skips_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    persist = AsyncMock(return_value=True)
    handle = AsyncMock()
    monkeypatch.setattr(
        "services.integrations.channel_capability_runtime.meta_dm_replies_enabled",
        lambda **_k: False,
    )
    monkeypatch.setattr(social_messaging_processor, "persist_skipped_social_inbound", persist)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)

    result = await social_messaging_processor.process_meta_social_event(
        _event(),
        _settings(),
        tenant_id="tenant-a",
        binding_id="bind-ig-1",
        simulation=True,
    )

    handle.assert_not_awaited()
    persist.assert_awaited_once()
    kwargs = persist.await_args.kwargs
    assert kwargs["reason"] == "dm_disabled"
    assert kwargs["tenant_id"] == "tenant-a"
    assert kwargs["channel"] == "instagram"
    assert kwargs["action_id"] == "respond_instagram_dm"
    assert kwargs["text"] == "مرحبا"
    assert result["reason"] == "dm_disabled"
    assert result["firestore_saved"] is True
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_no_text_persists_placeholder_and_skips_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    persist = AsyncMock(return_value=True)
    handle = AsyncMock()
    monkeypatch.setattr(
        "services.integrations.channel_capability_runtime.meta_dm_replies_enabled",
        lambda **_k: True,
    )
    monkeypatch.setattr(social_messaging_processor, "persist_skipped_social_inbound", persist)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)
    monkeypatch.setattr(
        social_messaging_processor,
        "get_user_state_from_firestore",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        social_messaging_processor,
        "_resolve_social_customer_display_name",
        AsyncMock(return_value="Tester"),
    )

    result = await social_messaging_processor.process_meta_social_event(
        _event(text=""),
        _settings(),
        tenant_id="tenant-a",
        binding_id="bind-ig-1",
        simulation=True,
    )

    handle.assert_not_awaited()
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["reason"] == "no_text"
    assert result["delivery"] == "no_text"
    assert result["firestore_saved"] is True


@pytest.mark.asyncio
async def test_persist_helper_saves_user_row_without_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, Any] = {}

    async def fake_save(user_id, role, text, *_a, **_k):
        saved["user_id"] = user_id
        saved["role"] = role
        saved["text"] = text
        saved["metadata"] = _k.get("metadata")
        config.user_data_whatsapp.setdefault(user_id, {})["current_conversation_id"] = "conv-ig-1"

    monkeypatch.setattr(
        "services.integrations.social.social_inbound_livechat.save_conversation_message_to_firestore",
        fake_save,
    )
    user_id = "tenant-a:instagram:ig-asset-1:igsid-tester"
    config.user_data_whatsapp.pop(user_id, None)
    ok = await persist_skipped_social_inbound(
        user_id=user_id,
        tenant_id="tenant-a",
        channel="instagram",
        binding_id="bind-ig-1",
        action_id="respond_instagram_dm",
        reason="dm_disabled",
        message_id="mid-body-secret",
        text="hello from ig",
        simulation=False,
    )
    assert ok is True
    assert saved["role"] == "user"
    assert saved["text"] == "hello from ig"
    assert saved["metadata"]["ai_skipped"] == "dm_disabled"
    assert saved["metadata"]["channel"] == "instagram"
    config.user_data_whatsapp.pop(user_id, None)


def test_inbound_log_hashes_mid_and_omits_body(capsys: pytest.CaptureFixture[str]) -> None:
    from services.integrations.social.social_inbound_livechat import log_social_inbound

    log_social_inbound(
        tenant_id="tenant-a",
        channel="instagram",
        binding_id="bind-ig-1",
        action_id="respond_instagram_dm",
        reason="dm_disabled",
        firestore_saved=True,
        message_id="mid-secret-body",
    )
    out = capsys.readouterr().out
    assert "tenant=tenant-a" in out
    assert "action_id=respond_instagram_dm" in out
    assert "reason=dm_disabled" in out
    assert "mid-secret-body" not in out
    assert hashed_message_id("mid-secret-body") in out
