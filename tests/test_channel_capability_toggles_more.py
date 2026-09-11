"""Continuation of channel capability toggle tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.channel_capability_state import (
    comment_capability_state,
)
from services.channel_capability_toggles import (
    enable_channel_defaults_after_connect,
    set_channel_toggle,
)
from services.cm.actions import (
    ACTION_FACEBOOK_COMMENTS,
    ACTION_FACEBOOK_DM,
    ACTION_INSTAGRAM_COMMENTS,
    ACTION_INSTAGRAM_DM,
    published_action_enabled,
)
from tests.test_channel_capability_toggles import (
    _Cred,
    _fb_binding,
    _Registry,
)


def test_tenant_isolation_bindings(monkeypatch) -> None:
    other = _fb_binding(tenant_id="other", asset_id="page-other")
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda tenant_id, platform: [] if tenant_id == "linas" else [other],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("pages_messaging",))),
    )
    state = comment_capability_state("linas", "facebook")
    assert state["status"] == "disabled"
    assert state["blocker_code"] == "connect_channel_first"


@pytest.mark.asyncio
async def test_disable_comments_keeps_dm_requested(monkeypatch) -> None:
    """Disable Comments path must not clear DM CM action (regression guard via unit stubs)."""

    calls: list[tuple[str, bool]] = []

    async def _sync(**kwargs):
        calls.append(("sync", kwargs["enabled"]))

    def _set_action(**kwargs):
        calls.append((kwargs["action_id"], kwargs["enabled"]))
        return SimpleNamespace()

    async def _publish(**_k):
        calls.append(("publish", True))

    monkeypatch.setattr("services.channel_capability_toggles._sync_comment_assets", _sync)
    monkeypatch.setattr("services.channel_capability_toggles._set_action_in_draft", _set_action)
    monkeypatch.setattr("services.channel_capability_toggles._publish_actions", _publish)
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda *_a, **_k: {"dm": True, "comments": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {"effective_enabled": False, "requested_enabled": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {"effective_enabled": True, "requested_enabled": True},
    )

    from services.channel_capability_toggles import set_channel_toggle

    result = await set_channel_toggle(
        tenant_id="linas",
        platform="facebook",
        toggle="comments",
        enabled=False,
        actor="test",
    )
    assert ("sync", False) in calls
    assert (ACTION_FACEBOOK_COMMENTS, False) in calls
    assert all(c[0] != ACTION_FACEBOOK_DM for c in calls if isinstance(c[0], str))
    assert result["toggles"]["dm"] is True
    assert result["toggles"]["comments"] is False


@pytest.mark.asyncio
async def test_toggle_dm_off_preserves_comments_when_only_published_exists(monkeypatch, tmp_path) -> None:
    """Regression: toggling one CM action must not reset the sibling action from schema defaults."""

    from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content

    install_mocked_openai_embeddings(monkeypatch)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("CM_PUBLISH_ENABLED", "1")

    tenant = "toggle_indep"
    await publish_test_content(
        tenant,
        {
            "actions": {
                "items": [
                    {"id": ACTION_FACEBOOK_DM, "enabled": True},
                    {"id": ACTION_FACEBOOK_COMMENTS, "enabled": True},
                    {"id": ACTION_INSTAGRAM_DM, "enabled": False},
                    {"id": ACTION_INSTAGRAM_COMMENTS, "enabled": False},
                ],
            }
        },
    )

    from services.cm.storage import draft_section_path

    assert not draft_section_path(tenant, "actions").exists()

    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._sync_comment_assets",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda *_a, **_k: {"dm": False, "comments": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {"effective_enabled": True, "requested_enabled": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {"effective_enabled": False, "requested_enabled": False},
    )

    await set_channel_toggle(
        tenant_id=tenant,
        platform="facebook",
        toggle="dm",
        enabled=False,
        actor="test",
    )

    assert published_action_enabled(tenant, ACTION_FACEBOOK_COMMENTS) is True
    assert published_action_enabled(tenant, ACTION_FACEBOOK_DM) is False


@pytest.mark.asyncio
async def test_toggle_comments_on_preserves_dm_when_only_published_exists(monkeypatch, tmp_path) -> None:
    from tests.cm_test_helpers import install_mocked_openai_embeddings, publish_test_content

    install_mocked_openai_embeddings(monkeypatch)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("CM_PUBLISH_ENABLED", "1")

    tenant = "linas"
    await publish_test_content(
        tenant,
        {
            "actions": {
                "items": [
                    {"id": ACTION_FACEBOOK_DM, "enabled": True},
                    {"id": ACTION_FACEBOOK_COMMENTS, "enabled": False},
                    {"id": ACTION_INSTAGRAM_DM, "enabled": False},
                    {"id": ACTION_INSTAGRAM_COMMENTS, "enabled": False},
                ],
            }
        },
    )

    from services.cm.storage import draft_section_path

    assert not draft_section_path(tenant, "actions").exists()

    monkeypatch.setattr(
        "services.channel_capability_toggles.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._sync_comment_assets",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._ensure_comment_webhooks_for_platform",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comments_enable_blocker",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda *_a, **_k: {"dm": True, "comments": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {"effective_enabled": True, "requested_enabled": True},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {"effective_enabled": True, "requested_enabled": True},
    )

    await set_channel_toggle(
        tenant_id=tenant,
        platform="facebook",
        toggle="comments",
        enabled=True,
        actor="test",
    )

    assert published_action_enabled(tenant, ACTION_FACEBOOK_DM) is True
    assert published_action_enabled(tenant, ACTION_FACEBOOK_COMMENTS) is True


@pytest.mark.asyncio
async def test_enable_channel_defaults_after_connect_enables_both(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def _set(**kwargs):
        calls.append((kwargs["toggle"], kwargs["enabled"]))
        return {
            "toggles": {"dm": True, "comments": True},
            "comments_state": {},
            "dm_state": {},
        }

    monkeypatch.setattr("services.channel_capability_toggles.set_channel_toggle", _set)

    await enable_channel_defaults_after_connect(
        tenant_id="linas",
        platform="facebook",
        actor="oauth",
    )
    assert calls == [("dm", True), ("comments", True)]
