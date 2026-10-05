"""IG/FB DM: V2 technical failures and greeting fail-soft (not validator copy)."""

from __future__ import annotations

import pytest

from services.ai_setup.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY, BRAIN_TEMPORARY_ERROR_MESSAGE_KEY
from services.owner_copilot.dynamic_messages_service import get_dynamic_message


@pytest.fixture(autouse=True)
def _reset_temp_error_debounce() -> None:
    from services.brain.temporary_error_debounce import reset_temporary_error_debounce_for_tests

    reset_temporary_error_debounce_for_tests()
    yield
    reset_temporary_error_debounce_for_tests()


def test_hi_kifak_still_evaluates_greeting_policy() -> None:
    from services.brain.contracts.turn import HistorySnapshot
    from services.brain.greeting_policy import evaluate_greeting

    decision = evaluate_greeting(
        tenant_id="t-greet",
        message="Hi kifak",
        history=HistorySnapshot(),
        language="ar",
    )
    assert decision.text != get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, "ar")


def test_greeting_without_owner_opener_does_not_emit_canned_copy() -> None:
    from services.brain.contracts.turn import HistorySnapshot
    from services.brain.greeting_policy import evaluate_greeting

    decision = evaluate_greeting(
        tenant_id="t-greet",
        message="Hi kifak",
        history=HistorySnapshot(),
        language="ar",
    )
    assert decision.eligible is False
    assert decision.text == ""
    assert "ما قدرت أتأكد" not in decision.text
    assert decision.text != get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, "ar")
    assert decision.text != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "ar")


def test_greeting_and_planner_modules_are_gone() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert not (root / "services/brain/agent/greeting_turn.py").exists()
    assert not (root / "services/brain/planner/openai_plan.py").exists()
    loop = (root / "services/brain/agent/loop.py").read_text(encoding="utf-8")
    assert "retrieval_skipped" in loop
    assert "run_terra_turn" in loop


@pytest.mark.asyncio
async def test_greeting_only_handler_fail_soft_is_not_temporary_error() -> None:
    from unittest.mock import AsyncMock, patch

    from services.brain.inbound.text_handlers_respond_reply import _handle_published_cm_runtime

    with patch(
        "services.brain.reply.orchestrator.run_customer_reply_v2_dm",
        new=AsyncMock(side_effect=RuntimeError("openai timeout")),
    ):
        reply, metadata = await _handle_published_cm_runtime(
            tenant_id="t-hello",
            message="Hello",
            detected_language="en",
            response_language="en",
            conversation_id="conv-hello-1",
        )
    assert reply == ""
    assert "Use this rule only" not in (reply or "")
    assert reply != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "en")
    assert metadata["customer_silence"] is True
    assert metadata["exception_class"] == "RuntimeError"


@pytest.mark.asyncio
async def test_faq_ask_brain_path_without_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.faq_exact import FaqExactHit
    from services.brain.gates import GateDecision
    from services.brain.reply.orchestrator import run_customer_reply_v2_dm

    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates",
        lambda turn, apply_credits=True, message="": GateDecision(True, "ok"),
    )
    monkeypatch.setattr(
        "services.brain.faq_turn.find_published_exact_faq",
        lambda _tid, _msg: FaqExactHit("faq1", "en", "hours?", "We open at 10.", 1),
    )
    out = await run_customer_reply_v2_dm(
        tenant_id="t-faq-ig",
        message="What are your hours?",
        conversation_id="c-faq",
        message_id="m-faq",
        user_id="u1",
        response_language="en",
    )
    assert out.reply
    assert "We open at 10." in (out.reply or "")
    assert out.reason != "v2_failed_closed"
    assert "temporary" not in (out.reply or "").lower()


@pytest.mark.asyncio
async def test_forced_runtime_error_temporary_error_once_then_silence() -> None:
    from unittest.mock import AsyncMock, patch

    from services.brain.inbound.text_handlers_respond_reply import _handle_published_cm_runtime

    with patch(
        "services.brain.reply.orchestrator.run_customer_reply_v2_dm",
        new=AsyncMock(side_effect=RuntimeError("forced boom")),
    ):
        first, meta1 = await _handle_published_cm_runtime(
            tenant_id="t-temp",
            message="How much does it cost?",
            detected_language="en",
            response_language="en",
            conversation_id="conv-temp-1",
        )
        second, meta2 = await _handle_published_cm_runtime(
            tenant_id="t-temp",
            message="How much does it cost?",
            detected_language="en",
            response_language="en",
            conversation_id="conv-temp-1",
        )
    expected = get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "en")
    assert first == ""
    assert first != expected
    assert meta1["exception_class"] == "RuntimeError"
    assert str(meta1.get("blocker") or "").startswith("RuntimeError:")
    assert meta1.get("customer_silence") is True
    assert second == ""
    assert meta2["exception_class"] == "RuntimeError"
    assert meta2.get("temporary_error_silenced") is True
