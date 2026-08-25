"""App DM/Comments switches persist locally; Comments ON also re-ensures Meta comment webhooks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.channel_capability_runtime import meta_dm_replies_enabled
from services.cm.actions import ACTION_FACEBOOK_DM


def test_unpublished_tenant_keeps_dm_replies_on(monkeypatch) -> None:
    monkeypatch.setattr("services.channel_capability_runtime.load_actions_section", lambda _tenant: None)
    assert meta_dm_replies_enabled(tenant_id="no_cm_pointer", platform="facebook") is True


def test_published_dm_off_stops_replies(monkeypatch) -> None:
    from services.cm.schemas import ActionCapability, ActionsSection

    monkeypatch.setattr(
        "services.channel_capability_runtime.load_actions_section",
        lambda _tenant: ActionsSection(items=[ActionCapability(id=ACTION_FACEBOOK_DM, enabled=False)]),
    )
    assert meta_dm_replies_enabled(tenant_id="linas", platform="facebook") is False


@pytest.mark.asyncio
async def test_enable_comments_ensures_comment_webhooks(monkeypatch) -> None:
    ensure_webhooks = AsyncMock()
    settings: list[bool] = []

    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [SimpleNamespace(app_key="linas_first_party", channel="facebook", asset_id="page-1")],
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.get_comment_reply_setting",
        lambda **_k: SimpleNamespace(enabled=False, instructions=""),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.set_comment_reply_setting",
        lambda **kwargs: settings.append(bool(kwargs["enabled"])),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._ensure_comment_webhooks_for_platform",
        ensure_webhooks,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._set_action_in_draft",
        lambda **_k: SimpleNamespace(),
    )
    monkeypatch.setattr("services.channel_capability_toggles._publish_actions", AsyncMock())
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda *_a, **_k: {"dm": True, "comments": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {"requested_enabled": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {"requested_enabled": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comments_enable_blocker",
        lambda *_a, **_k: "missing_comment_permissions",
    )

    from services.channel_capability_toggles import set_channel_toggle

    result = await set_channel_toggle(
        tenant_id="linas",
        platform="facebook",
        toggle="comments",
        enabled=True,
        actor="test",
    )
    ensure_webhooks.assert_awaited_once_with(tenant_id="linas", platform="facebook")
    assert settings == [True]
    assert result["toggles"]["comments"] is True
