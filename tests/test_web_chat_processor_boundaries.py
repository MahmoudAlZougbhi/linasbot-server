"""Regression tests for Web Chat producer/consumer API boundaries."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.adapters.web import WebFollowUpAdapter
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.credit_fsm import tenant_scoped_user_data
from services.web_chat.processor import _persist_web_turn
from services.web_chat.session_authority import issue_session_authority
from services.web_chat.store_pg import WebChatPgStore
from tests.web_chat_acceptance_support import patch_web_chat_store, seed_acceptance_widget


def _followup_visitor_setup(
    store: WebChatPgStore,
    *,
    visitor_id: str,
    tenant_id: str = "tenant-b",
) -> WebChatWidgetConfig:
    widget_key, tid = seed_acceptance_widget(store, tenant_id=tenant_id)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    return widget


@pytest.mark.asyncio
async def test_persist_web_turn_passes_tenant_scoped_user_data_to_log_interaction(tmp_path, monkeypatch) -> None:
    save_mock = AsyncMock(return_value=("web:tenant-z:visitor-tenant", None))
    log_mock = MagicMock()
    monkeypatch.setattr("services.web_chat.persistence.save_conversation_message_to_firestore", save_mock)
    monkeypatch.setattr("services.interaction_flow_logger.is_flow_logging_enabled", lambda: True)
    monkeypatch.setattr("services.interaction_flow_logger.log_interaction", log_mock)

    user_id = "web:visitor-tenant"
    widget = WebChatWidgetConfig(
        tenant_id="tenant-z",
        widget_key="wk-z",
        site_url="https://shop.example.com",
        enabled=True,
        created_at=time.time(),
        updated_at=time.time(),
    )
    await _persist_web_turn(
        tenant_id="tenant-z",
        user_id=user_id,
        conversation_id="web:tenant-z:visitor-tenant",
        visitor_id="visitor-tenant",
        user_text="Hello",
        reply_text="Hi",
        widget=widget,
    )

    log_mock.assert_called_once()
    assert log_mock.call_args.kwargs["user_data"]["tenant_id"] == "tenant-z"
    expected = tenant_scoped_user_data(tenant_id="tenant-z", user_id=user_id, visitor_id="visitor-tenant")
    assert log_mock.call_args.kwargs["user_data"] == expected


@pytest.mark.asyncio
async def test_web_followup_adapter_persistence_failure_leaves_no_pending_message(
    tmp_path, monkeypatch, acceptance_ha_env
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    _followup_visitor_setup(store, visitor_id="visitor-3")

    from services.web_chat.persistence import PersistFailure

    persist_mock = AsyncMock(side_effect=PersistFailure("firestore_error", "firestore down"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel="web_chat",
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-3",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="idem-3",
    )
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:visitor-3",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-3",
    )

    result = await WebFollowUpAdapter().send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="idem-3",
    )

    assert result.status == "failed"
    session = store.get_visitor("visitor-3")
    assert session is not None
    assert len(session.pending_assistant) == 0


@pytest.mark.asyncio
async def test_persist_web_turn_uses_firestore_save_signature(tmp_path, monkeypatch) -> None:
    save_mock = AsyncMock(return_value=("web:tenant-a:visitor-1", None))
    monkeypatch.setattr("services.web_chat.persistence.save_conversation_message_to_firestore", save_mock)

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
        user_id="web:visitor-1",
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
    assert user_call["metadata"]["tenant_id"] == "tenant-a"
    assert ai_call["role"] == "ai"
    assert ai_call["metadata"]["handled_by"] == "ai"


@pytest.mark.asyncio
async def test_web_followup_adapter_send_followup_result_shape(tmp_path, monkeypatch, acceptance_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    widget = _followup_visitor_setup(store, visitor_id="visitor-2")

    from services.web_chat.persistence import PersistOutcome, PersistResult

    persist_mock = AsyncMock(
        return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="web:tenant-b:visitor-2")
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    from tests.test_web_followup_web_delivery import _reserve_followup_credit

    job = WhatsAppSmartFollowUpJob(
        tenant_id=widget.tenant_id,
        channel="web_chat",
        connection_id=widget.widget_key,
        conversation_id=f"web:{widget.tenant_id}:visitor-2",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="idem-1",
    )
    job.reservation_id = _reserve_followup_credit(tenant_id=widget.tenant_id, idem="idem-1")
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id=widget.tenant_id,
        conversation_id=f"web:{widget.tenant_id}:visitor-2",
        connection_id=widget.widget_key,
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
    persist_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_followup_adapter_missing_visitor_returns_skipped(monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
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
