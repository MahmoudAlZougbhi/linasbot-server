"""Dashboard counts, Live Chat filter, capability pending, IG/FB regression."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from services.channel_capability_state import action_id_for, supported_platforms
from services.channel_capability_toggles import attach_channel_toggles
from services.customer_reply_v2.channel_metadata import parse_channel
from services.integration_capabilities import list_tenant_integration_status
from services.live_chat_channel import live_chat_channel_matches, resolve_live_chat_channel
from services.social_user_id import compose_social_user_id
from services.tenant_mobile_dashboard.activity import build_activity_summary
from services.tiktok_business.config import REQUESTED_SCOPES, tiktok_redirect_uri, tiktok_webhook_callback_url
from services.tiktok_business.scopes import messaging_send_ready
from tests.tiktok_business.conftest import seed_connection


def test_production_urls() -> None:
    assert tiktok_redirect_uri() == "https://www.linasaibot.com/oauth/tiktok/callback"
    assert tiktok_webhook_callback_url() == "https://www.linasaibot.com/webhooks/tiktok"
    assert "user.info.basic" in REQUESTED_SCOPES
    assert "comment.list.manage" in REQUESTED_SCOPES
    assert "message.list.read" not in REQUESTED_SCOPES


def test_dashboard_counts_from_logs_only() -> None:
    now = time.time()
    iso = datetime.fromtimestamp(now, tz=UTC).isoformat()
    entries = [
        {
            "tenant_id": "t-dash-tt",
            "channel": "tiktok_comment",
            "source": "tiktok_comment",
            "handler_path": "tiktok_business.comment_ai",
            "outcome": "ok",
            "bot_to_user": "thanks",
            "timestamp": iso,
            "tokens": 10,
        },
        {
            "tenant_id": "t-dash-tt",
            "channel": "tiktok",
            "source": "tiktok_dm",
            "handler_path": "tiktok_business.messaging",
            "outcome": "ok",
            "bot_to_user": "hello",
            "timestamp": iso,
            "tokens": 8,
        },
        {
            "tenant_id": "other",
            "channel": "tiktok_comment",
            "outcome": "ok",
            "bot_to_user": "nope",
            "timestamp": iso,
        },
    ]
    payload = build_activity_summary(
        "t-dash-tt",
        start_ts=now - 50,
        end_ts=now + 50,
        integrations=[{"platform": "tiktok", "connected": True, "coming_soon": False}],
        entries=entries,
    )
    tiktok = next(row for row in payload["channels"] if row["platform"] == "tiktok")
    assert tiktok["coming_soon"] is False
    assert tiktok["comments"] == 1
    assert tiktok["messages"] == 1
    ig = next(row for row in payload["channels"] if row["platform"] == "instagram")
    assert ig["messages"] == 0
    assert ig["comments"] == 0


def test_live_chat_tiktok_filter() -> None:
    user_id = compose_social_user_id(tenant_id="shop-1", channel="tiktok", asset_id="conn-1", sender_id="cust-9")
    assert "tiktok" in user_id
    assert resolve_live_chat_channel(user_id) == "tiktok"
    assert live_chat_channel_matches({"user_id": user_id}, "tiktok") is True
    assert live_chat_channel_matches({"user_id": "instagram:1"}, "tiktok") is False


def test_messaging_capability_pending_without_scopes() -> None:
    assert messaging_send_ready(["comment.list", "comment.list.manage"]) is False
    assert messaging_send_ready(["message.list.read", "message.list.send"]) is True


def test_parse_channel_tiktok_not_instagram() -> None:
    platform, surface, public = parse_channel("tiktok_comment")
    assert platform == "tiktok"
    assert surface == "comment"
    assert public is True
    dm_platform, dm_surface, dm_public = parse_channel("tiktok")
    assert dm_platform == "tiktok"
    assert dm_surface == "dm"
    assert dm_public is False


def test_ig_fb_supported_platforms_unchanged() -> None:
    assert supported_platforms() == ("instagram", "facebook")
    assert action_id_for("instagram", "dm") == "respond_instagram_dm"
    assert action_id_for("facebook", "comments") == "respond_facebook_comments"


def test_ig_fb_integration_rows_not_coming_soon() -> None:
    rows = list_tenant_integration_status("linas")
    ig = next(r for r in rows if r["platform"] == "instagram")
    fb = next(r for r in rows if r["platform"] == "facebook")
    assert ig["coming_soon"] is False
    assert fb["coming_soon"] is False
    assert ig["connectable"] is True
    tt = next(r for r in rows if r["platform"] == "tiktok")
    assert tt["coming_soon"] is False
    snap = next(r for r in rows if r["platform"] == "snapchat")
    assert snap["coming_soon"] is True


def test_attach_toggles_skips_coming_soon_tiktok_stub() -> None:
    rows = [
        {"platform": "instagram", "label": "Instagram", "connected": True, "coming_soon": False},
        {"platform": "tiktok", "label": "TikTok", "connected": False, "coming_soon": True},
    ]
    out = attach_channel_toggles(rows, tenant_id="linas")
    assert "toggles" in out[0]
    assert "toggles" not in out[1]


def test_fail_closed_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    monkeypatch.delenv("TIKTOK_CLIENT_SECRET", raising=False)
    from services.tiktok_business.config import get_tiktok_settings, require_tiktok_settings
    from services.tiktok_business.errors import TikTokNotConfiguredError

    assert get_tiktok_settings().configured is False
    with pytest.raises(TikTokNotConfiguredError):
        require_tiktok_settings()


def test_health_does_not_require_tiktok() -> None:
    from services.tiktok_business.health import tiktok_business_readiness

    payload = tiktok_business_readiness()
    assert payload["ok"] is True
    assert payload["required"] is False


def test_connected_identity_in_status(tt_db) -> None:
    seed_connection(tt_db)
    from services.tiktok_business.status import tiktok_integration_row

    row = tiktok_integration_row("linas")
    assert row["connected"] is True
    assert row["account"]["username"] == "linas_tt"
    assert row["account"]["display_name"] == "Linas TT"
