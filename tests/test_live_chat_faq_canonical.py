"""Live Chat no longer reaches local_qa; Like→FAQ uses canonical CM FAQ."""

from __future__ import annotations

from pathlib import Path

from services.live_chat.service import live_chat_service

ROOT = Path(__file__).resolve().parents[1]
LIVE_CHAT_ROOT = ROOT / "services" / "live_chat"
LIVE_CHAT_ROUTES = (
    "/api/live-chat/unified-chats",
    "/api/live-chat/takeover",
    "/api/live-chat/release",
    "/api/live-chat/events",
    "/api/live-chat/mark-read",
    "/api/live-chat/send-message",
    "/api/live-chat/operator-status",
    "/api/live-chat/conversation/{user_id}/{conversation_id}",
    "/api/live-chat/end-conversation",
)


def _live_chat_python() -> list[Path]:
    return sorted(LIVE_CHAT_ROOT.rglob("*.py"))


def test_live_chat_has_no_local_qa_runtime() -> None:
    forbidden = ("local_qa", "read_qa_pairs", "modules.local_qa_api")
    for path in _live_chat_python():
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} still mentions {token}"


def test_faq_match_context_removed_from_live_chat() -> None:
    assert not hasattr(live_chat_service, "get_faq_match_context")
    assert not hasattr(live_chat_service, "update_message_content")
    assert callable(live_chat_service.get_conversation_details)
    details = (LIVE_CHAT_ROOT / "service_details.py").read_text(encoding="utf-8")
    assert "get_faq_match_context" not in details
    assert "published_faq_entry" not in details


def test_live_chat_http_contracts_preserved() -> None:
    from modules import live_chat_api

    src = Path("modules/live_chat_api.py").read_text(encoding="utf-8")
    for route in LIVE_CHAT_ROUTES:
        assert route in src, route
    assert "faq-match-context" not in src
    assert callable(live_chat_api.get_unified_chats)
    assert callable(live_chat_api.get_conversation_details)
    assert callable(live_chat_api.send_operator_message)
    assert callable(live_chat_api.takeover_conversation) or "takeover" in src


def test_like_faq_writes_canonical_cm_faq() -> None:
    from inspect import getsource

    from modules import cm_faq_api
    from services.faq.cm_faq import create_faq_pair_from_livechat

    src = getsource(cm_faq_api.cm_faq_from_livechat)
    assert "/api/cm/faq/from-livechat" in Path("modules/cm_faq_api.py").read_text(encoding="utf-8")
    assert "create_faq_pair_from_livechat" in src
    assert "local_qa" not in src
    writer = getsource(create_faq_pair_from_livechat)
    assert "create_faq_pair(" in writer
    assert "local_qa" not in writer
    mobile = Path("mobile/linas-ai/src/features/livechat/liveChatApi.ts").read_text(encoding="utf-8")
    assert "/api/cm/faq/from-livechat" in mobile
    assert "saveFaqFromLiveChat" in mobile
