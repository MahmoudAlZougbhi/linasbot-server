"""IG/FB DM: V2 technical failures and greeting fail-soft (not validator copy)."""

from __future__ import annotations

import pytest

from services.ai_setup.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY, BRAIN_TEMPORARY_ERROR_MESSAGE_KEY
from services.brain.greeting import is_greeting_only, safe_greeting_text
from services.owner_copilot.dynamic_messages_service import get_dynamic_message


def test_hi_kifak_is_greeting_only() -> None:
    assert is_greeting_only("Hi kifak") is True
    assert is_greeting_only("Hi, what time do you open?") is False


def test_safe_greeting_never_uses_validator_or_temporary_copy() -> None:
    text = safe_greeting_text(tenant_id="t-greet", message="Hi kifak", language="ar")
    assert text.strip()
    assert "ما قدرت أتأكد" not in text
    assert text != get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, "ar")
    assert text != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "ar")


@pytest.mark.asyncio
async def test_identity_greeting_openai_failure_sends_catalog_opener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.brain.agent.greeting_turn import identity_greeting_result
    from services.brain.contracts.turn import CustomerTurn

    async def boom(*_a, **_k):
        raise RuntimeError("openai timeout")

    monkeypatch.setattr("services.brain.agent.greeting_turn.openai_configured", lambda: True)
    monkeypatch.setattr(
        "services.brain.agent.greeting_turn._identity_context",
        lambda _turn: "IDENTITY\nname=Test",
    )
    monkeypatch.setattr(
        "services.billing.membership.provider_expense.record_pending_provider",
        lambda **_k: None,
    )
    monkeypatch.setattr("services.brain.providers.config.answer_model", lambda: "gpt-test")
    monkeypatch.setattr("services.brain.billing.operation_id_for_turn", lambda _turn: "op-test")
    monkeypatch.setattr(
        "services.brain.llm_core_service.create_chat_completion",
        boom,
    )
    monkeypatch.setattr("services.brain.conversation_store.remember_turn", lambda *_a, **_k: None)
    turn = CustomerTurn(
        tenant_id="t-greet-llm",
        conversation_id="c1",
        event_ids=["m1"],
        extra={"response_language": "ar"},
    )
    out = await identity_greeting_result(turn, message="Hi kifak", channel="instagram_dm")
    assert out is not None
    assert out.envelope.decision == "reply"
    text = out.envelope.messages[0].text
    assert text.strip()
    assert "ما قدرت أتأكد" not in text
    assert (out.extra or {}).get("path") == "identity_greeting_fail_soft"
    assert out.ai_called is False
    assert text != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "ar")
