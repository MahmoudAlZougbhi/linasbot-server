"""Web Live Chat operator send uses the visitor outbox, never WhatsApp."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.live_chat_operator_text_delivery import operator_media_not_supported
from services.live_chat_operator_web_delivery import (
    deliver_web_operator_text,
    parse_web_visitor_session_id,
    web_operator_media_not_supported,
)
from services.live_chat_service import live_chat_service


def test_parse_web_visitor_session_id() -> None:
    assert parse_web_visitor_session_id("web:visitor-1") == "visitor-1"
    assert parse_web_visitor_session_id("web:visitor-1", "web:linas:visitor-1") == "visitor-1"
    assert parse_web_visitor_session_id("web:x", "web:shop:sess-99") == "x"


def test_web_operator_media_not_supported() -> None:
    result = web_operator_media_not_supported()
    assert result["success"] is False
    assert result["delivered"] is False
    assert "not supported" in result["error"].lower()


def test_operator_media_blocked_for_tiktok_and_web() -> None:
    tiktok = operator_media_not_supported("tiktok:cust", "image")
    assert tiktok is not None
    assert tiktok["success"] is False
    web = operator_media_not_supported("web:visitor", "voice")
    assert web is not None
    assert web["channel"] == "web"
    assert operator_media_not_supported("instagram:1", "image") is None
    assert operator_media_not_supported("+96170123456", "image") is None
    unknown = operator_media_not_supported("unlabeled", "image")
    assert unknown is not None
    assert unknown["error"] == "unknown_channel"


def test_deliver_web_operator_text_enqueues_outbox() -> None:
    store = MagicMock()
    store.queue_assistant_message.return_value = True
    with patch("services.web_chat.store.web_chat_store", store):
        result = deliver_web_operator_text(
            user_id="web:visitor-1",
            conversation_id="web:linas:visitor-1",
            text="hello from staff",
            idempotency_key="op-1",
        )
    assert result["success"] is True
    assert result["delivered"] is True
    store.queue_assistant_message.assert_called_once_with(
        "visitor-1",
        "hello from staff",
        idempotency_key="op-1",
    )


def test_deliver_web_duplicate_idempotency_is_success() -> None:
    store = MagicMock()
    store.queue_assistant_message.return_value = False
    with patch("services.web_chat.store.web_chat_store", store):
        result = deliver_web_operator_text(
            user_id="web:visitor-1",
            conversation_id="web:linas:visitor-1",
            text="hello from staff",
            idempotency_key="op-1",
        )
    assert result["success"] is True
    assert result["duplicate"] is True


def test_deliver_web_missing_session_is_honest_failure() -> None:
    store = MagicMock()
    store.queue_assistant_message.side_effect = KeyError("session not found")
    with patch("services.web_chat.store.web_chat_store", store):
        result = deliver_web_operator_text(
            user_id="web:missing",
            conversation_id="web:linas:missing",
            text="hello",
        )
    assert result["success"] is False
    assert result["delivered"] is False
    assert result["error"] == "web_session_not_found"


def _send_patches(*extra: object):
    pause_result = MagicMock(activated=True, already_active=False, control_epoch=3)
    return (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("web:visitor-1", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=pause_result,
        ),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
        *extra,
    )


@pytest.mark.asyncio
async def test_web_operator_send_enqueues_and_never_calls_whatsapp() -> None:
    store = MagicMock()
    store.queue_assistant_message.return_value = True
    adapter = MagicMock()
    adapter.send_text_message = AsyncMock()

    def boom(*_a, **_k):
        raise AssertionError("WhatsApp Postgres must not open for Web Live Chat")

    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.web_chat.store.web_chat_store", store),
            patch("db.session.whatsapp_session", side_effect=boom),
        ):
            stack.enter_context(cm)
        result = await live_chat_service.send_operator_message(
            conversation_id="web:linas:visitor-1",
            user_id="web:visitor-1",
            message="hello visitor",
            operator_id="op1",
            adapter=adapter,
            tenant_id="linas",
            idempotency_key="k1",
        )
    assert result.get("success") is True
    assert result.get("delivered") is True
    assert result.get("status") == "human"
    store.queue_assistant_message.assert_called_once()
    adapter.send_text_message.assert_not_called()


@pytest.mark.asyncio
async def test_web_enqueue_failure_undoes_fresh_pause() -> None:
    store = MagicMock()
    store.queue_assistant_message.side_effect = RuntimeError("outbox down")
    resume = AsyncMock(return_value=MagicMock(control_epoch=4, already_active=False, audit_recorded=False))
    adapter = MagicMock()
    adapter.send_text_message = AsyncMock()

    with ExitStack() as stack:
        for cm in _send_patches(
            patch("services.web_chat.store.web_chat_store", store),
            patch("services.requests.manual_mode.resume_manual_mode", resume),
        ):
            stack.enter_context(cm)
        result = await live_chat_service.send_operator_message(
            conversation_id="web:linas:visitor-1",
            user_id="web:visitor-1",
            message="hello visitor",
            operator_id="op1",
            adapter=adapter,
            tenant_id="linas",
        )
    assert result.get("success") is False
    assert result.get("delivered") is False
    assert result.get("manual_mode_undone_after_failed_delivery") is True
    assert result.get("status") == "bot"
    resume.assert_awaited_once()
    adapter.send_text_message.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_channel_text_does_not_call_whatsapp() -> None:
    adapter = MagicMock()
    adapter.send_text_message = AsyncMock()
    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("unlabeled", None)),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=MagicMock(activated=True, already_active=False, control_epoch=1),
        ),
        patch.object(live_chat_service, "_refresh_index_for_conversation", new_callable=AsyncMock),
        patch(
            "services.requests.manual_mode.resume_manual_mode",
            new_callable=AsyncMock,
            return_value=MagicMock(control_epoch=2, already_active=False, audit_recorded=False),
        ),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-unknown",
            user_id="unlabeled",
            message="hello",
            operator_id="op1",
            adapter=adapter,
            tenant_id="linas",
        )
    assert result.get("success") is False
    assert "unknown_channel" in str(result.get("error") or "")
    adapter.send_text_message.assert_not_called()


@pytest.mark.asyncio
async def test_tiktok_media_rejected_before_pause() -> None:
    activate = AsyncMock()
    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("services.requests.manual_mode.activate_manual_mode", activate),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c-tt",
            user_id="tiktok:cust",
            message="YmFzZTY0",
            operator_id="op1",
            adapter=MagicMock(),
            message_type="image",
            tenant_id="linas",
        )
    assert result.get("success") is False
    assert "not supported" in str(result.get("error") or "").lower()
    activate.assert_not_awaited()
