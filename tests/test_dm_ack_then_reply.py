"""Feature-flagged customer DM ack-then-final. Flag default off."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from services.brain.contracts.turn import CustomerTurn
from services.brain.inbound.ack_then_reply import (
    ack_line_is_safe,
    ack_then_reply_enabled,
    bind_customer_ack_sender,
    emit_bound_ack,
    maybe_send_heavy_turn_ack,
)
from services.brain.inbound.text_handlers_respond_phase2 import text_handlers_respond_phase2


def test_ack_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_DM_ACK_THEN_REPLY", raising=False)
    assert ack_then_reply_enabled("whatsapp") is False
    assert ack_then_reply_enabled("web_chat") is False


def test_ack_flag_channel_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_DM_ACK_THEN_REPLY", "1")
    monkeypatch.delenv("CUSTOMER_DM_ACK_CHANNELS", raising=False)
    assert ack_then_reply_enabled("instagram") is True
    monkeypatch.setenv("CUSTOMER_DM_ACK_CHANNELS", "whatsapp,web_chat")
    assert ack_then_reply_enabled("whatsapp") is True
    assert ack_then_reply_enabled("instagram") is False


def test_ack_line_never_carries_invented_facts() -> None:
    assert ack_line_is_safe("لحظة بشوفلك") is True
    assert ack_line_is_safe("One sec, checking") is True
    assert ack_line_is_safe("The laser is 50") is False
    assert ack_line_is_safe("Open from 9 to 5") is False
    assert ack_line_is_safe("") is False


@pytest.mark.asyncio
async def test_flag_off_skips_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_DM_ACK_THEN_REPLY", raising=False)
    sent: list[str] = []

    async def send_fn(_uid: str, text: str | None = None, **_k: Any) -> dict[str, Any]:
        sent.append(str(text or ""))
        return {"success": True}

    user_data: dict[str, Any] = {}
    turn = CustomerTurn(
        tenant_id="t1",
        conversation_id="c1",
        extra={"response_language": "ar", "_ack_fixture": "لحظة بشوفلك"},
    )
    async with bind_customer_ack_sender(user_id="u1", user_data=user_data, send_message_func=send_fn):
        out = await maybe_send_heavy_turn_ack(turn, message="شو سعر الليزر", channel="whatsapp")
    assert out == ""
    assert sent == []


@pytest.mark.asyncio
async def test_flag_on_sends_one_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_DM_ACK_THEN_REPLY", "1")
    sent: list[str] = []

    async def send_fn(_uid: str, text: str | None = None, **_k: Any) -> dict[str, Any]:
        sent.append(str(text or ""))
        return {"success": True}

    user_data: dict[str, Any] = {}
    turn = CustomerTurn(
        tenant_id="t1",
        conversation_id="c1",
        extra={"response_language": "ar", "_ack_fixture": "لحظة بشوفلك"},
    )
    async with bind_customer_ack_sender(user_id="u1", user_data=user_data, send_message_func=send_fn):
        out = await maybe_send_heavy_turn_ack(turn, message="شو سعر الليزر", channel="whatsapp")
        again = await maybe_send_heavy_turn_ack(turn, message="شو سعر الليزر", channel="whatsapp")
    assert out == "لحظة بشوفلك"
    assert again == ""
    assert sent == ["لحظة بشوفلك"]
    assert user_data.get("_dm_ack_in_flight") is None


@pytest.mark.asyncio
async def test_phase2_flag_on_ack_then_final(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_DM_ACK_THEN_REPLY", "1")
    sent: list[str] = []

    async def send_fn(_uid: str, text: str | None = None, **_k: Any) -> dict[str, Any]:
        sent.append(str(text or ""))
        return {"success": True}

    async def fake_runtime(**_k: Any) -> tuple[str, dict[str, Any]]:
        await emit_bound_ack("One sec, checking")
        return "final evidence reply", {
            "reason": "v2_generated",
            "ai_called": True,
            "validated": True,
            "pipeline_decisions": [{"step": "customer_reply_v2", "decision": "ai_generated", "ai_called": True}],
        }

    ctx: dict[str, Any] = {
        "_handle_published_cm_runtime": fake_runtime,
        "current_conversation_id": "c-ack",
        "current_gender": "unknown",
        "current_preferred_lang": "en",
        "log_interaction": mock.Mock(),
        "response_language": "en",
        "save_conversation_message_to_firestore": mock.AsyncMock(),
        "send_message_func": send_fn,
        "user_data": {"tenant_id": "t-ack", "channel": "web_chat", "phone_number": "room:1"},
        "user_id": "web:ack",
        "user_image_base64": None,
        "user_input_to_process": "what is the price of x",
        "user_name": "Test",
    }
    monkeypatch.setattr("services.ai_setup.constants.tenant_uses_cm_runtime", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "services.brain.inbound.text_handlers_respond_phase2.settle_after_outbound",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.brain.inbound.text_handlers_respond_phase2.settle_reserved_credits",
        lambda *_a, **_k: None,
    )
    result = await text_handlers_respond_phase2(ctx)
    assert result == "_PHASE_HALT"
    assert sent == ["One sec, checking", "final evidence reply"]


@pytest.mark.asyncio
async def test_phase2_flag_off_single_final(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_DM_ACK_THEN_REPLY", raising=False)
    sent: list[str] = []

    async def send_fn(_uid: str, text: str | None = None, **_k: Any) -> dict[str, Any]:
        sent.append(str(text or ""))
        return {"success": True}

    async def fake_runtime(**_k: Any) -> tuple[str, dict[str, Any]]:
        return "final only", {
            "reason": "v2_generated",
            "ai_called": True,
            "validated": True,
            "pipeline_decisions": [],
        }

    ctx: dict[str, Any] = {
        "_handle_published_cm_runtime": fake_runtime,
        "current_conversation_id": "c-ack-off",
        "current_gender": "unknown",
        "current_preferred_lang": "en",
        "log_interaction": mock.Mock(),
        "response_language": "en",
        "save_conversation_message_to_firestore": mock.AsyncMock(),
        "send_message_func": send_fn,
        "user_data": {"tenant_id": "t-ack", "channel": "web_chat"},
        "user_id": "web:ack-off",
        "user_image_base64": None,
        "user_input_to_process": "hello",
        "user_name": "Test",
    }
    monkeypatch.setattr("services.ai_setup.constants.tenant_uses_cm_runtime", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "services.brain.inbound.text_handlers_respond_phase2.settle_after_outbound",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.brain.inbound.text_handlers_respond_phase2.settle_reserved_credits",
        lambda *_a, **_k: None,
    )
    result = await text_handlers_respond_phase2(ctx)
    assert result == "_PHASE_HALT"
    assert sent == ["final only"]
