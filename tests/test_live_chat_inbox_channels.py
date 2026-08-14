"""Live Chat inbox must return real WhatsApp / Instagram / Facebook / TikTok channels."""

from __future__ import annotations

from services.live_chat_channel import (
    live_chat_channel_matches,
    normalize_live_chat_channel,
    resolve_live_chat_channel,
)
from services.live_chat_contracts import utc_now
from services.live_chat_service import live_chat_service


def test_resolve_channel_from_user_id_prefixes() -> None:
    assert resolve_live_chat_channel("instagram:178414000") == "instagram"
    assert resolve_live_chat_channel("linas:facebook:page:sender") == "facebook"
    assert resolve_live_chat_channel("tenant-a:instagram:ig:psid") == "instagram"
    assert resolve_live_chat_channel("tiktok:open_id") == "tiktok"
    assert resolve_live_chat_channel("whatsapp:+96170123456") == "whatsapp"
    assert resolve_live_chat_channel("+96170123456") == "whatsapp"


def test_resolve_channel_from_customer_info_not_user_id() -> None:
    assert (
        resolve_live_chat_channel(
            "numeric-psid",
            {"customer_info": {"channel": "instagram_dm"}},
        )
        == "instagram"
    )
    assert (
        resolve_live_chat_channel(
            "psid",
            {"customer_info": {"channel": "facebook"}},
        )
        == "facebook"
    )


def test_never_invents_tiktok_for_whatsapp_or_meta() -> None:
    assert resolve_live_chat_channel("+96170123456") != "tiktok"
    assert resolve_live_chat_channel("instagram:1") != "tiktok"
    assert resolve_live_chat_channel("facebook:1") != "tiktok"
    assert resolve_live_chat_channel("someone", {"customer_info": {"name": "TikTok Fan"}}) != "tiktok"
    assert normalize_live_chat_channel("all") is None
    assert live_chat_channel_matches({"user_id": "instagram:1"}, "all") is True
    assert live_chat_channel_matches({"user_id": "instagram:1"}, "instagram") is True
    assert live_chat_channel_matches({"user_id": "instagram:1"}, "tiktok") is False
    assert live_chat_channel_matches({"user_id": "tiktok:ready"}, "tiktok") is True


def test_frontend_format_and_index_entry_expose_channel() -> None:
    svc = live_chat_service
    conv = {
        "conversation_id": "conv-ig",
        "customer_info": {"name": "Sara", "channel": "instagram"},
        "last_message_text": "hi",
        "last_message_at": utc_now(),
        "message_count": 1,
        "human_takeover_active": False,
    }
    entry = svc._build_index_entry("instagram:99", conv, [])
    assert entry["channel"] == "instagram"
    formatted = svc._to_frontend_chat_format(
        {
            "conversation_id": "conv-fb",
            "user_id": "facebook:55",
            "last_message_text": "yo",
            "last_message_at": utc_now().isoformat(),
            "conversation_state": svc.STATE_BOT_ACTIVE,
        }
    )
    assert formatted["channel"] == "facebook"
    wa = svc._to_frontend_chat_format(
        {
            "conversation_id": "conv-wa",
            "user_id": "+96170111111",
            "last_message_text": "hello",
            "last_message_at": utc_now().isoformat(),
            "conversation_state": svc.STATE_BOT_ACTIVE,
        }
    )
    assert wa["channel"] == "whatsapp"
    assert wa["channel"] != "tiktok"


def test_unified_chats_api_declares_channel_query() -> None:
    from pathlib import Path

    src = Path("modules/live_chat_api.py").read_text(encoding="utf-8")
    assert 'channel: str = Query(default="all"' in src
    assert "channel=channel" in src
    unified = Path("services/live_chat_service_unified.py").read_text(encoding="utf-8")
    assert "wanted_channel" in unified
    assert '"channel": row_channel' in unified
    assert "if not search_val and not cursor and not state_values and not wanted_channel:" in unified
    assert "tiktok" in Path("services/live_chat_channel.py").read_text(encoding="utf-8")


def test_unlabeled_index_rows_stay_visible_on_all() -> None:
    unlabeled = {"user_id": "+96170123456", "last_message_text": "hi"}
    assert live_chat_channel_matches(unlabeled, "all") is True
    assert live_chat_channel_matches(unlabeled, "whatsapp") is True
    ig = {"user_id": "psid", "customer_info": {"channel": "instagram_dm"}}
    assert live_chat_channel_matches(ig, "all") is True
    assert live_chat_channel_matches(ig, "instagram") is True
    assert live_chat_channel_matches(ig, "tiktok") is False
