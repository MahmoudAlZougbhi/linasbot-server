"""Web Chat AI stays silent while Live Chat takeover is active."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.web_chat.takeover_gate import (
    WebChatTakeoverState,
    maybe_silence_web_chat_for_takeover,
    read_web_chat_takeover_state,
)


def _widget() -> SimpleNamespace:
    return SimpleNamespace(widget_key="widget-1")


@pytest.mark.asyncio
async def test_firestore_error_allows_ai() -> None:
    with patch("utils.utils.get_firestore_db", side_effect=RuntimeError("fs down")):
        state = await read_web_chat_takeover_state(user_id="web:v1", conversation_id="web:linas:v1")
    assert state.active is False


@pytest.mark.asyncio
async def test_assigned_takeover_skips_ai_without_waiting_notice() -> None:
    queued: list[tuple] = []

    async def fake_read(**_k: object) -> WebChatTakeoverState:
        return WebChatTakeoverState(active=True, operator_id="op-9")

    def fake_queue(visitor_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        queued.append((visitor_id, content, idempotency_key))
        return True

    with (
        patch("services.web_chat.takeover_gate.read_web_chat_takeover_state", fake_read),
        patch("services.web_chat.store.web_chat_store.queue_assistant_message", fake_queue),
    ):
        silenced = await maybe_silence_web_chat_for_takeover(
            tenant_id="linas",
            user_id="web:v1",
            conversation_id="web:linas:v1",
            visitor_id="v1",
            inbound_text="hi staff",
            widget=_widget(),
        )
    assert silenced is True
    assert queued == []


@pytest.mark.asyncio
async def test_waiting_takeover_queues_notice_and_skips_ai() -> None:
    queued: list[tuple] = []

    async def fake_read(**_k: object) -> WebChatTakeoverState:
        return WebChatTakeoverState(active=True, operator_id=None)

    def fake_queue(visitor_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        queued.append((visitor_id, content, idempotency_key))
        return True

    with (
        patch("services.web_chat.takeover_gate.read_web_chat_takeover_state", fake_read),
        patch("services.web_chat.store.web_chat_store.queue_assistant_message", fake_queue),
        patch("services.web_chat.takeover_gate._persist_web_projection", new_callable=AsyncMock),
        patch("services.web_chat.takeover_gate._waiting_notice", return_value="please wait"),
    ):
        silenced = await maybe_silence_web_chat_for_takeover(
            tenant_id="linas",
            user_id="web:v1",
            conversation_id="web:linas:v1",
            visitor_id="v1",
            inbound_text="hi",
            widget=_widget(),
        )
    assert silenced is True
    assert len(queued) == 1
    assert queued[0][0] == "v1"
    assert queued[0][1] == "please wait"


@pytest.mark.asyncio
async def test_inactive_takeover_allows_ai() -> None:
    async def fake_read(**_k: object) -> WebChatTakeoverState:
        return WebChatTakeoverState(active=False, operator_id=None)

    with patch("services.web_chat.takeover_gate.read_web_chat_takeover_state", fake_read):
        silenced = await maybe_silence_web_chat_for_takeover(
            tenant_id="linas",
            user_id="web:v1",
            conversation_id="web:linas:v1",
            visitor_id="v1",
            inbound_text="hi",
            widget=_widget(),
        )
    assert silenced is False


@pytest.mark.asyncio
async def test_generate_web_reply_skips_customer_ai_when_silenced() -> None:
    from services.web_chat.processor_v2_reply import generate_web_chat_reply_text

    run_ai = AsyncMock()
    with (
        patch("services.web_chat.takeover_gate.maybe_silence_web_chat_for_takeover", AsyncMock(return_value=True)),
        patch("services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm", run_ai),
    ):
        reply = await generate_web_chat_reply_text(
            tid="linas",
            text="hello",
            conversation_id="web:linas:v1",
            widget=_widget(),
            visitor_id="v1",
            user_id="web:v1",
            word_notice=None,
            reply_precheck=SimpleNamespace(allowed=True),
            credit=MagicMock(),
            runtime=MagicMock(),
        )
    assert reply == ""
    run_ai.assert_not_awaited()
