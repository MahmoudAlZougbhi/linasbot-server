"""Channel capability toggles for mobile Integrations (CM Actions)."""

from __future__ import annotations

from types import SimpleNamespace

from services.channel_capability_toggles import (
    action_id_for,
    attach_channel_toggles,
    channel_toggle_states,
    comment_capability_state,
)
from services.cm.actions import (
    ACTION_FACEBOOK_COMMENTS,
    ACTION_FACEBOOK_DM,
    ACTION_INSTAGRAM_COMMENTS,
    ACTION_INSTAGRAM_DM,
)


def test_action_ids_match_cm_schema() -> None:
    assert action_id_for("instagram", "dm") == ACTION_INSTAGRAM_DM
    assert action_id_for("instagram", "comments") == ACTION_INSTAGRAM_COMMENTS
    assert action_id_for("facebook", "dm") == ACTION_FACEBOOK_DM
    assert action_id_for("facebook", "comments") == ACTION_FACEBOOK_COMMENTS
    assert action_id_for("tiktok", "dm") is None


def test_attach_toggles_only_on_meta_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_toggles.channel_toggle_states",
        lambda _tenant, platform: {"dm": platform == "instagram", "comments": False},
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda _tenant, platform: {
            "requested_enabled": False,
            "permission_present": platform != "instagram",
            "webhook_subscribed": False,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": ["instagram_manage_comments"] if platform == "instagram" else [],
            "blocker": "missing_comment_permissions" if platform == "instagram" else "connect_channel_first",
            "status": "needs_permission" if platform == "instagram" else "off",
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
    assert out[1]["toggles"] == {"dm": False, "comments": False}
    assert out[1]["comments_blocker"] == "connect_channel_first"
    assert "toggles" not in out[2]


def test_channel_toggle_states_defaults_when_unpublished(monkeypatch) -> None:
    monkeypatch.setattr("services.channel_capability_toggles.load_actions_section", lambda _tid: None)
    monkeypatch.setattr(
        "services.channel_capability_toggles.comment_capability_state",
        lambda *_a, **_k: {
            "requested_enabled": False,
            "permission_present": False,
            "webhook_subscribed": False,
            "live_verified": False,
            "effective_enabled": False,
            "missing_scopes": [],
            "blocker": "connect_channel_first",
            "status": "off",
        },
    )
    assert channel_toggle_states("linas", "facebook") == {"dm": False, "comments": False}


def test_comment_capability_state_never_effective_without_permissions(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_toggles._comments_action_requested",
        lambda *_a, **_k: True,
    )
    binding = SimpleNamespace(
        tenant_id="linas",
        channel="instagram",
        status="active",
        app_key="app_a",
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
        asset_id="ig1",
        binding_id="b1",
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._active_channel_bindings",
        lambda *_a, **_k: [binding],
    )

    class _Cred:
        scopes = ("instagram_basic", "instagram_manage_messages")

    class _Registry:
        def get_credential(self, _binding):
            return _Cred()

    monkeypatch.setattr(
        "services.channel_capability_toggles.get_meta_app_registry",
        lambda: _Registry(),
    )
    state = comment_capability_state("linas", "instagram")
    assert state["requested_enabled"] is True
    assert state["permission_present"] is False
    assert state["live_verified"] is False
    assert state["effective_enabled"] is False
    assert state["blocker"] == "missing_comment_permissions"
    assert "instagram_manage_comments" in state["missing_scopes"]


def test_comment_capability_state_effective_only_when_all_gates_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.channel_capability_toggles._comments_action_requested",
        lambda *_a, **_k: True,
    )
    binding = SimpleNamespace(
        tenant_id="linas",
        channel="facebook",
        status="active",
        app_key="app_a",
        auth_flow="facebook_login",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
        asset_id="page1",
        binding_id="b2",
    )
    monkeypatch.setattr(
        "services.channel_capability_toggles._active_channel_bindings",
        lambda *_a, **_k: [binding],
    )

    class _Cred:
        scopes = (
            "pages_messaging",
            "pages_read_user_content",
            "pages_manage_engagement",
        )

    class _Registry:
        def get_credential(self, _binding):
            return _Cred()

    monkeypatch.setattr(
        "services.channel_capability_toggles.get_meta_app_registry",
        lambda: _Registry(),
    )
    state = comment_capability_state("linas", "facebook")
    assert state["permission_present"] is True
    assert state["webhook_subscribed"] is True
    assert state["live_verified"] is False
    assert state["effective_enabled"] is True
    assert state["status"] == "ready"
    assert state["blocker"] is None
