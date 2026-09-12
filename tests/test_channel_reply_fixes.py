"""Channel reply regressions: no email leak, no empty bubbles, no invented takeover."""

from __future__ import annotations

from services.live_chat_contracts import utc_now
from services.live_chat_service import live_chat_service
from services.takeover_customer_notice import customer_human_handover_notice, public_staff_label


def test_public_staff_label_never_returns_email() -> None:
    assert public_staff_label("mahmoudalzougbhi@gmail.com") == "Mahmoudalzougbhi"
    assert public_staff_label("Mohammad Ali", "m@x.com") == "Mohammad Ali"
    assert "@" not in public_staff_label("self@linas.ai")
    assert public_staff_label("", None, "  ") == ""


def test_customer_handover_notice_comes_from_ai_setup_not_email() -> None:
    notice = customer_human_handover_notice("en")
    assert notice
    assert "@" not in notice
    assert "mahmoudalzougbhi@gmail.com" not in notice.lower()
    assert "The conversation has been transferred to" not in notice


def test_inbox_omits_empty_last_message_preview() -> None:
    formatted = live_chat_service._to_frontend_chat_format(
        {
            "conversation_id": "conv-empty",
            "user_id": "instagram:99",
            "last_message_text": "   ",
            "last_message_at": utc_now().isoformat(),
            "conversation_state": live_chat_service.STATE_BOT_ACTIVE,
        }
    )
    assert formatted["last_message"] is None


def test_live_chat_hides_empty_text_only_bubbles() -> None:
    visible = live_chat_service._visible_chat_messages(
        [
            {"role": "user", "text": "hi", "type": "text"},
            {"role": "ai", "text": "", "content": "", "type": "text"},
            {"role": "ai", "text": "", "type": "image", "image_url": "https://x/img.jpg"},
        ]
    )
    assert len(visible) == 2
    assert visible[0]["text"] == "hi"
    assert visible[1]["type"] == "image"


def test_meta_adapter_skips_whitespace_only_send() -> None:
    import asyncio

    from services.meta_messaging import MetaMessagingAdapter

    adapter = MetaMessagingAdapter(
        access_token="unit-token",
        account_id="378696005334409",
        channel="facebook",
    )

    async def boom(*_a, **_k):
        raise AssertionError("Graph must not be called for empty text")

    adapter._post = boom  # type: ignore[method-assign]
    result = asyncio.run(adapter.send_text_message("PSID1", "   "))
    assert result["success"] is False
    assert result["error"] == "empty_text"
