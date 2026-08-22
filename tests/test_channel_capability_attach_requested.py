"""Integrations GET must not persist Comments OFF for a connected channel."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.channel_capability_toggles import attach_channel_toggles, sync_published_comment_assets_if_enabled


def test_attach_keeps_requested_comments_on_when_permissions_missing(monkeypatch) -> None:
    writes: list[dict] = []

    def _set_action(**kwargs):
        writes.append(kwargs)
        raise AssertionError("attach must not persist comments off")

    monkeypatch.setattr("services.channel_capability_toggles._set_action_in_draft", _set_action)
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": True,
            "permission_present": True,
            "webhook_subscribed": True,
            "tenant_action_enabled": True,
            "connection_healthy": True,
            "live_verified": True,
            "effective_enabled": True,
            "missing_scopes": [],
            "blocker_code": None,
            "blocker": None,
            "status": "enabled",
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": True,
            "permission_present": False,
            "webhook_subscribed": False,
            "tenant_action_enabled": True,
            "connection_healthy": True,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": ["pages_manage_engagement"],
            "blocker_code": "missing_comment_permissions",
            "blocker": "missing_comment_permissions",
            "status": "permission_required",
        },
    )
    rows = [{"platform": "facebook", "label": "Facebook", "connected": True, "coming_soon": False}]
    out = attach_channel_toggles(rows, tenant_id="linas")
    assert writes == []
    assert out[0]["toggles"] == {"dm": True, "comments": True}
    assert out[0]["comments_state"]["requested_enabled"] is True
    assert out[0]["comments_state"]["effective_enabled"] is False
    assert out[0]["comments_blocker"] == "missing_comment_permissions"


@pytest.mark.asyncio
async def test_connect_sync_turns_local_comment_assets_on_when_switch_is_on(monkeypatch) -> None:
    clear = AsyncMock(return_value=True)
    sync_assets = AsyncMock()
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": True,
            "permission_present": False,
            "connection_healthy": True,
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.clear_invalid_comments_enabled_state_async",
        clear,
    )
    monkeypatch.setattr("services.channel_capability_toggles._sync_comment_assets", sync_assets)

    await sync_published_comment_assets_if_enabled(tenant_id="linas", platform="facebook")
    clear.assert_not_called()
    sync_assets.assert_awaited_once()
