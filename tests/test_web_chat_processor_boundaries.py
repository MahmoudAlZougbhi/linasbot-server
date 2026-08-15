"""Regression tests for Web Chat producer/consumer API boundaries."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.adapters.web import WebFollowUpAdapter
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.processor import _persist_web_turn
from services.web_chat.store import WebChatStore


@pytest.mark.asyncio
async def test_persist_web_turn_uses_firestore_save_signature(tmp_path, monkeypatch) -> None:
    save_mock = AsyncMock()
    monkeypatch.setattr("utils.utils.save_conversation_message_to_firestore", save_mock)

    import config

    user_id = "web:visitor-1"
    config.user_data_whatsapp.pop(user_id, None)

    widget = WebChatWidgetConfig(
        tenant_id="tenant-a",
        widget_key="wk-test",
        site_url="https://shop.example.com",
        enabled=True,
        created_at=time.time(),
        updated_at=time.time(),
    )
    await _persist_web_turn(
        tenant_id="tenant-a",
        user_id=user_id,
        conversation_id="web:tenant-a:visitor-1",
        visitor_id="visitor-1",
        user_text="Hello",
        reply_text="Hi there",
        widget=widget,
    )

    assert save_mock.await_count == 2
    user_call = save_mock.await_args_list[0].kwargs
    ai_call = save_mock.await_args_list[1].kwargs
    assert user_call["role"] == "user"
    assert user_call["text"] == "Hello"
    assert user_call["conversation_id"] == "web:tenant-a:visitor-1"
    assert ai_call["role"] == "ai"
    assert ai_call["text"] == "Hi there"
    assert ai_call["metadata"]["handled_by"] == "ai"


@pytest.mark.asyncio
async def test_web_followup_adapter_send_followup_result_shape(tmp_path, monkeypatch) -> None:
    store = WebChatStore(root=tmp_path / "web_chat")
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    widget = WebChatWidgetConfig(
        tenant_id="tenant-b",
        widget_key="wk-b",
        site_url="https://shop.example.com",
        enabled=True,
        created_at=time.time(),
        updated_at=time.time(),
    )
    store.get_or_create_visitor(session_id="visitor-2", widget=widget, greeting="Hi")

    save_mock = AsyncMock()
    monkeypatch.setattr("utils.utils.save_conversation_message_to_firestore", save_mock)

    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel="web_chat",
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-2",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="idem-1",
    )
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:visitor-2",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-2",
    )

    result = await WebFollowUpAdapter().send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="idem-1",
    )

    assert isinstance(result, FollowUpSendResult)
    assert result.status == "sent"
    assert result.reason == "sent"
    assert result.provider_message_id == "idem-1"
    save_mock.assert_awaited_once()
    assert save_mock.await_args.kwargs["role"] == "ai"
    assert save_mock.await_args.kwargs["metadata"]["handled_by"] == "smart_followup"


@pytest.mark.asyncio
async def test_web_followup_adapter_missing_visitor_returns_skipped() -> None:
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:missing",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="",
    )
    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel="web_chat",
        connection_id="wk-b",
        conversation_id="web:tenant-b:missing",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="idem-2",
    )

    result = await WebFollowUpAdapter().send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="idem-2",
    )

    assert result.status == "skipped"
    assert result.reason == "missing_visitor"
