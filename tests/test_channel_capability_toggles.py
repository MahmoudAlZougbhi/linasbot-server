"""Canonical channel capability matrix (DMs + Comments)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.channel_capability_state import (
    comment_capability_state,
    dm_capability_state,
)
from services.channel_capability_toggles import (
    action_id_for,
    attach_channel_toggles,
    channel_toggle_states,
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
from services.meta_app_registry import APP_A_KEY


def test_action_ids_match_cm_schema() -> None:
    assert action_id_for("instagram", "dm") == ACTION_INSTAGRAM_DM
    assert action_id_for("instagram", "comments") == ACTION_INSTAGRAM_COMMENTS
    assert action_id_for("facebook", "dm") == ACTION_FACEBOOK_DM
    assert action_id_for("facebook", "comments") == ACTION_FACEBOOK_COMMENTS
    assert action_id_for("tiktok", "dm") is None


def test_attach_toggles_only_on_meta_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda _tenant, platform: {
            "requested_enabled": platform == "instagram",
            "permission_present": True,
            "webhook_subscribed": True,
            "tenant_action_enabled": platform == "instagram",
            "connection_healthy": True,
            "live_verified": platform == "instagram",
            "effective_enabled": platform == "instagram",
            "missing_scopes": [],
            "blocker_code": None,
            "blocker": None,
            "status": "enabled" if platform == "instagram" else "ready",
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda _tenant, platform: {
            "requested_enabled": False,
            "permission_present": platform != "instagram",
            "webhook_subscribed": False,
            "tenant_action_enabled": False,
            "connection_healthy": True,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": ["instagram_manage_comments"] if platform == "instagram" else [],
            "blocker_code": "missing_comment_permissions" if platform == "instagram" else "connect_channel_first",
            "blocker": "missing_comment_permissions" if platform == "instagram" else "connect_channel_first",
            "status": "permission_required" if platform == "instagram" else "disabled",
        },
    )
    rows = [
        {"platform": "instagram", "label": "Instagram", "connected": True, "coming_soon": False},
        {"platform": "facebook", "label": "Facebook", "connected": False, "coming_soon": False},
        {"platform": "tiktok", "label": "TikTok", "connected": False, "coming_soon": True},
    ]
    out = attach_channel_toggles(rows, tenant_id="linas")
    assert out[0]["toggles"] == {"dm": True, "comments": False}
    assert out[0]["comments_blocker"] == "missing_comment_permissions"
    assert out[0]["comments_state"]["permission_present"] is False
    assert out[0]["comments_state"]["effective_enabled"] is False
    assert "dm_state" in out[0]
    assert out[1]["toggles"] == {"dm": False, "comments": False}
    assert out[1]["comments_blocker"] == "connect_channel_first"
    assert "toggles" not in out[2]


def test_channel_toggle_states_defaults_when_unpublished(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": False,
            "permission_present": False,
            "webhook_subscribed": False,
            "tenant_action_enabled": False,
            "connection_healthy": False,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": [],
            "blocker_code": "connect_channel_first",
            "blocker": "connect_channel_first",
            "status": "disabled",
        },
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.dm_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": False,
            "permission_present": False,
            "webhook_subscribed": False,
            "tenant_action_enabled": False,
            "connection_healthy": False,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": [],
            "blocker_code": "connect_channel_first",
            "blocker": "connect_channel_first",
            "status": "disabled",
        },
    )
    assert channel_toggle_states("linas", "facebook") == {"dm": False, "comments": False}


def _fb_binding(**kwargs):
    base = dict(
        tenant_id="linas",
        channel="facebook",
        status="active",
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
        asset_id="page1",
        binding_id="b2",
        page_id="page1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ig_binding(**kwargs):
    base = dict(
        tenant_id="linas",
        channel="instagram",
        status="active",
        app_key=APP_A_KEY,
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
        asset_id="ig1",
        binding_id="b1",
        page_id="page1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class _Cred:
    def __init__(self, scopes, *, token="tok", expires_at=None):
        self.scopes = scopes
        self.access_token = token
        self.expires_at = expires_at


class _Registry:
    def __init__(self, cred: _Cred):
        self._cred = cred

    def get_credential(self, _binding):
        return self._cred


def test_comment_capability_false_toggle_never_effective_without_permissions(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_ig_binding(webhook_subscribed_fields=("messages", "messaging_postbacks"))],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("instagram_basic", "instagram_manage_messages"))),
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    state = comment_capability_state("linas", "instagram")
    assert state["requested_enabled"] is True
    assert state["permission_present"] is False
    assert state["live_verified"] is False
    assert state["effective_enabled"] is False
    assert state["blocker_code"] == "missing_comment_permissions"
    assert "instagram_manage_comments" in state["missing_scopes"]
    assert state["last_checked_at"] > 0


def test_comment_capability_meta_approval_when_advanced_access_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding(webhook_subscribed_fields=("messages", "messaging_postbacks"))],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("pages_messaging",))),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    # Public tenant without Advanced Access stays blocked.
    state = comment_capability_state("customer_gym", "facebook")
    assert state["permission_present"] is False
    assert state["status"] == "meta_approval_required"
    assert state["blocker_code"] == "meta_approval_required"
    assert state["effective_enabled"] is False
    assert state["live_verified"] is False


def test_comment_capability_linas_missing_scopes_not_meta_approval(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding(webhook_subscribed_fields=("messages", "messaging_postbacks"))],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("pages_messaging",))),
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: False)
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    state = comment_capability_state("linas", "facebook")
    assert state["permission_present"] is False
    assert state["blocker_code"] == "missing_comment_permissions"
    assert state["status"] == "permission_required"
    assert state["effective_enabled"] is False


def test_comment_capability_effective_only_when_all_gates_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(
            _Cred(
                (
                    "pages_messaging",
                    "pages_read_user_content",
                    "pages_manage_engagement",
                )
            )
        ),
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    state = comment_capability_state("linas", "facebook")
    assert state["connection_healthy"] is True
    assert state["permission_present"] is True
    assert state["webhook_subscribed"] is True
    assert state["tenant_action_enabled"] is True
    assert state["live_verified"] is False
    assert state["effective_enabled"] is True
    assert state["status"] == "enabled"
    assert state["blocker_code"] is None


def test_comment_capability_ready_when_gates_pass_but_not_requested(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("pages_messaging", "pages_read_user_content", "pages_manage_engagement"))),
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    state = comment_capability_state("linas", "facebook")
    assert state["status"] == "ready"
    assert state["effective_enabled"] is False


def test_comment_capability_webhook_setup_required(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding(webhook_subscribed_fields=("messages", "messaging_postbacks"))],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(_Cred(("pages_messaging", "pages_read_user_content", "pages_manage_engagement"))),
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    state = comment_capability_state("linas", "facebook")
    assert state["status"] == "webhook_setup_required"
    assert state["blocker_code"] == "missing_comment_webhook"


def test_comment_capability_unhealthy_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding()],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(
            _Cred(
                ("pages_messaging", "pages_read_user_content", "pages_manage_engagement"),
                expires_at=1,
            )
        ),
    )
    monkeypatch.setattr(
        "services.channel_capability_state._tenant_comment_assets_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr("services.channel_capability_state._advanced_access_approved", lambda: True)
    state = comment_capability_state("linas", "facebook")
    assert state["connection_healthy"] is False
    assert state["effective_enabled"] is False
    assert state["status"] == "reauthorization_required"


def test_dm_capability_effective_when_requested_and_healthy(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_state._action_requested",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.channel_capability_state.canonical_channel_bindings",
        lambda *_a, **_k: [_fb_binding(webhook_subscribed_fields=("messages", "messaging_postbacks"))],
    )
    monkeypatch.setattr(
        "services.channel_capability_state.get_meta_app_registry",
        lambda: _Registry(
            _Cred(
                (
                    "pages_show_list",
                    "pages_manage_metadata",
                    "pages_read_engagement",
                    "pages_messaging",
                )
            )
        ),
    )
    state = dm_capability_state("linas", "facebook")
    assert state["effective_enabled"] is True
    assert state["live_verified"] is True
    assert state["status"] == "live_verified"


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
