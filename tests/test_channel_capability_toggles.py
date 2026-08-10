"""Channel capability toggles for mobile Integrations (CM Actions)."""

from __future__ import annotations

from services.channel_capability_toggles import (
    action_id_for,
    attach_channel_toggles,
    channel_toggle_states,
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
        "services.channel_capability_toggles.comments_enable_blocker",
        lambda _tenant, platform: "missing_comment_permissions" if platform == "instagram" else None,
    )
    rows = [
        {"platform": "instagram", "label": "Instagram", "connected": True, "coming_soon": False},
        {"platform": "facebook", "label": "Facebook", "connected": False, "coming_soon": False},
        {"platform": "tiktok", "label": "TikTok", "connected": False, "coming_soon": True},
    ]
    out = attach_channel_toggles(rows, tenant_id="linas")
    assert out[0]["toggles"] == {"dm": True, "comments": False}
    assert out[0]["comments_blocker"] == "missing_comment_permissions"
    assert out[1]["toggles"] == {"dm": False, "comments": False}
    assert "comments_blocker" not in out[1]
    assert "toggles" not in out[2]


def test_channel_toggle_states_defaults_when_unpublished(monkeypatch) -> None:
    monkeypatch.setattr("services.channel_capability_toggles.load_actions_section", lambda _tid: None)
    assert channel_toggle_states("linas", "facebook") == {"dm": False, "comments": False}
