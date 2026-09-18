"""Outbound IG/FB/web-chat must not send SOP / identity instruction dumps."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.ai_setup.constants import BRAIN_TEMPORARY_ERROR_MESSAGE_KEY
from services.ai_setup.schemas import DynamicMessageRecord, DynamicMessagesSection
from services.brain.compose.blocks import compose_evidence_context
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan, PlannerTask
from services.brain.greeting import evaluate_greeting, published_opener_text
from services.brain.identity import IdentityBundle
from services.brain.outbound_safety import is_customer_safe_opener, looks_like_instruction_text
from services.owner_copilot.dynamic_messages_service import get_dynamic_message

_SOP = (
    "Arabic-specific rule: مروى / المساعدة الذكية / ليناز ليزر\n"
    "Use this rule only if the user message is only a casual greeting.\n"
    "If the user message is not a casual greeting, process the message according to the knowledge base."
)


def test_sop_fixture_is_instruction_not_opener() -> None:
    assert looks_like_instruction_text(_SOP) is True
    assert is_customer_safe_opener(_SOP) is False
    assert is_customer_safe_opener("Hello! How can I help you today?") is True


def test_polluted_dynamic_message_is_not_sent_as_hello(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.greeting.load_dynamic_messages",
        lambda _tid: DynamicMessagesSection(
            items=[
                DynamicMessageRecord(
                    id="sop",
                    enabled=True,
                    trigger_mode="session_start",
                    en=_SOP,
                    ar=_SOP,
                )
            ]
        ),
    )
    from services.brain.history import build_history_snapshot

    history = build_history_snapshot([{"id": "m1", "role": "user", "text": "Hello"}], current_inbound_id="m1")
    decision = evaluate_greeting(
        tenant_id="linas-polluted",
        message="Hello",
        history=history,
        language="en",
        now=datetime.now(UTC),
    )
    assert decision.eligible is False
    text = published_opener_text(tenant_id="linas-polluted", message="Hello", language="en", history=history)
    assert "Use this rule only" not in text
    assert "Arabic-specific rule" not in text
    assert text != get_dynamic_message(BRAIN_TEMPORARY_ERROR_MESSAGE_KEY, "en")


def test_greeting_context_omits_advanced_instructions() -> None:
    identity = IdentityBundle(
        assistant_name="Marwa",
        business_name="Linas Laser",
        advanced_instructions=_SOP,
        greeting_behavior=_SOP,
        short_introduction=_SOP,
        identity_summary=_SOP,
        style_body=_SOP,
    )
    blob = compose_evidence_context(
        identity=identity,
        plan=PlannerPlan(tasks=[PlannerTask(id="greet", type="acknowledgement")]),
        bundle=EvidenceBundle(outcome="not_found"),
        greeting_turn=True,
    )
    assert "advanced=" not in blob
    assert "Use this rule only" not in blob
    assert "Arabic-specific rule" not in blob
    full = compose_evidence_context(
        identity=identity,
        plan=PlannerPlan(tasks=[PlannerTask(id="t1", type="information")]),
        bundle=EvidenceBundle(outcome="not_found"),
        greeting_turn=False,
    )
    assert "advanced=" in full


@pytest.mark.asyncio
async def test_identity_llm_sop_echo_falls_back_to_safe_greeting(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.agent.greeting_turn import identity_greeting_result
    from services.brain.contracts.turn import CustomerTurn

    class _Msg:
        content = _SOP

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    async def echo(*_a, **_k):
        return _Resp()

    monkeypatch.setattr("services.brain.agent.greeting_turn.openai_configured", lambda: True)
    monkeypatch.setattr(
        "services.brain.agent.greeting_turn._identity_context",
        lambda _turn: "IDENTITY\nname=Marwa",
    )
    monkeypatch.setattr(
        "services.billing.membership.provider_expense.record_pending_provider",
        lambda **_k: None,
    )
    monkeypatch.setattr("services.brain.providers.config.answer_model", lambda: "gpt-test")
    monkeypatch.setattr("services.brain.billing.operation_id_for_turn", lambda _turn: "op-test")
    monkeypatch.setattr("services.brain.llm_core_service.create_chat_completion", echo)
    monkeypatch.setattr("services.brain.conversation_store.remember_turn", lambda *_a, **_k: None)
    turn = CustomerTurn(
        tenant_id="t-sop-llm",
        conversation_id="c1",
        event_ids=["m1"],
        extra={"response_language": "ar"},
    )
    out = await identity_greeting_result(turn, message="Hello", channel="instagram_dm")
    assert out is not None
    assert out.stop_reason == "failed_closed"
    assert not out.envelope.messages


def test_apply_greeting_does_not_prepend_sop() -> None:
    from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage
    from services.brain.contracts.turn import CustomerTurn
    from services.brain.turn_pipeline import _apply_greeting

    turn = CustomerTurn(tenant_id="t1", invocation_kind="dm")
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination="dm", text="Full body is 299 USD.")],
    )
    out = _apply_greeting(turn, "how much is full body?", "instagram_dm", envelope)
    assert [item.text for item in out.messages] == ["Full body is 299 USD."]
    assert turn.state.greeted is False
