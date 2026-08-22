"""Channel capability disconnect / CONNECT_REQUIRED guards."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_enable_dm_requires_connected_channel(monkeypatch) -> None:
    from services.channel_capability_toggles import ChannelToggleError, set_channel_toggle

    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [],
    )
    with pytest.raises(ChannelToggleError) as exc:
        await set_channel_toggle(
            tenant_id="linas",
            platform="instagram",
            toggle="dm",
            enabled=True,
            actor="test",
        )
    assert exc.value.code == "CONNECT_REQUIRED"


@pytest.mark.asyncio
async def test_clear_toggles_after_disconnect_forces_dm_off(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {
            "toggles": {"dm": False, "comments": False},
            "comments_state": {"requested_enabled": False, "effective_enabled": False},
            "dm_state": {"requested_enabled": False, "effective_enabled": False},
        }

    monkeypatch.setattr(
        "services.channel_capability_disconnect.canonical_channel_bindings",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.dm_capability_state",
        lambda *_a, **_k: {"requested_enabled": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.comment_capability_state",
        lambda *_a, **_k: {"requested_enabled": True},
    )
    monkeypatch.setattr("services.channel_capability_disconnect.set_channel_toggle", _set)

    from services.channel_capability_disconnect import clear_channel_toggles_after_disconnect

    ok = await clear_channel_toggles_after_disconnect(tenant_id="linas", platform="instagram", actor="test")
    assert ok is True
    assert ("comments", False) in calls
    assert ("dm", False) in calls


@pytest.mark.asyncio
async def test_clear_invalid_dm_when_disconnected(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {
            "toggles": {"dm": False, "comments": False},
            "comments_state": {},
            "dm_state": {"requested_enabled": False},
        }

    monkeypatch.setattr(
        "services.channel_capability_disconnect.dm_capability_state",
        lambda *_a, **_k: {"requested_enabled": True, "connection_healthy": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.canonical_channel_bindings",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr("services.channel_capability_disconnect.set_channel_toggle", _set)

    from services.channel_capability_disconnect import clear_invalid_dm_enabled_state_async

    ok = await clear_invalid_dm_enabled_state_async(tenant_id="linas", platform="facebook", actor="test")
    assert ok is True
    assert calls == [("dm", False)]


@pytest.mark.asyncio
async def test_clear_invalid_dm_keeps_on_when_unhealthy_but_connected(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {}

    monkeypatch.setattr(
        "services.channel_capability_disconnect.dm_capability_state",
        lambda *_a, **_k: {"requested_enabled": True, "connection_healthy": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.canonical_channel_bindings",
        lambda *_a, **_k: [{"binding_id": "ig-1"}],
    )
    monkeypatch.setattr("services.channel_capability_disconnect.set_channel_toggle", _set)

    from services.channel_capability_disconnect import clear_invalid_dm_enabled_state_async

    ok = await clear_invalid_dm_enabled_state_async(tenant_id="linas", platform="instagram", actor="test")
    assert ok is False
    assert calls == []


@pytest.mark.asyncio
async def test_clear_invalid_comments_when_disconnected(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {
            "toggles": {"dm": False, "comments": False},
            "comments_state": {"requested_enabled": False},
            "dm_state": {},
        }

    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {"requested_enabled": True, "permission_present": False, "connection_healthy": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr("services.channel_capability_toggles.set_channel_toggle", _set)

    from services.channel_capability_toggles import clear_invalid_comments_enabled_state_async

    ok = await clear_invalid_comments_enabled_state_async(tenant_id="linas", platform="facebook", actor="test")
    assert ok is True
    assert calls == [("comments", False)]


@pytest.mark.asyncio
async def test_clear_invalid_comments_keeps_on_when_connected(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {}

    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": True,
            "permission_present": False,
            "connection_healthy": False,
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [{"binding_id": "fb-1"}],
    )
    monkeypatch.setattr("services.channel_capability_toggles.set_channel_toggle", _set)

    from services.channel_capability_toggles import clear_invalid_comments_enabled_state_async

    ok = await clear_invalid_comments_enabled_state_async(tenant_id="linas", platform="facebook", actor="test")
    assert ok is False
    assert calls == []
