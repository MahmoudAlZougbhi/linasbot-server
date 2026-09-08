from types import SimpleNamespace

from modules.api_security import required_permission_for, resolve_permissions
from services.access_channels import (
    allowed_channels_for_session,
    effective_inbox_channel,
    filter_chats_for_session,
    session_can_use_channel,
)


def _session(role: str = "operator", permissions: dict | None = None):
    return SimpleNamespace(role=role, permissions=permissions, tenant_id="t1", user_id="u1")


def test_comments_routes_use_view_and_manage_keys() -> None:
    assert required_permission_for("GET", "/api/comments/media") == "comments"
    assert required_permission_for("GET", "/api/comments/watchlist") == "comments"
    assert required_permission_for("GET", "/api/comments/media/123/threads") == "comments"
    assert required_permission_for("PATCH", "/api/comments/watchlist") == "commentsManage"


def test_operator_defaults_include_comments_and_channels() -> None:
    perms = resolve_permissions("operator", None)
    assert perms["comments"] is True
    assert perms["commentsManage"] is True
    assert perms["channelWhatsapp"] is True
    assert perms["channelInstagram"] is True


def test_missing_channel_keys_stay_on_for_custom_maps() -> None:
    perms = resolve_permissions("operator", {"liveChat": True, "dashboard": True})
    assert perms["channelWhatsapp"] is True
    assert perms["comments"] is True


def test_channel_filter_hides_other_inboxes() -> None:
    session = _session(
        permissions={
            "channelWhatsapp": True,
            "channelInstagram": False,
            "channelFacebook": False,
            "channelTiktok": False,
            "channelWeb": False,
        }
    )
    allowed = allowed_channels_for_session(session)
    assert allowed == frozenset({"whatsapp"})
    assert session_can_use_channel(session, "whatsapp") is True
    assert session_can_use_channel(session, "instagram") is False
    assert effective_inbox_channel(session, "all") == "whatsapp"
    assert effective_inbox_channel(session, "instagram") is None
    payload = filter_chats_for_session(
        session,
        {"chats": [{"channel": "whatsapp"}, {"channel": "instagram"}]},
    )
    assert [row["channel"] for row in payload["chats"]] == ["whatsapp"]


def test_admin_sees_every_channel() -> None:
    session = _session(role="admin", permissions={"channelWhatsapp": False})
    assert allowed_channels_for_session(session) is None
    assert session_can_use_channel(session, "tiktok") is True
    assert effective_inbox_channel(session, "instagram") == "instagram"
