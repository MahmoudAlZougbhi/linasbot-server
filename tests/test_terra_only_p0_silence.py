"""Terra-only P0: system canned emitters gone; fail paths silence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.brain.templates import brain_template, owner_protocol_text
from services.integrations.web_chat.processor import default_greeting

ROOT = Path(__file__).resolve().parents[1]


def test_brain_template_tables_are_gone() -> None:
    src = (ROOT / "services/brain/templates.py").read_text(encoding="utf-8")
    for needle in (
        "_HANDOFF",
        "_CONFIRM",
        "_VISUAL_DISABLED",
        "_NO_EVIDENCE",
        "_NO_EVIDENCE_HANDOFF",
        "_FAQ_AMBIGUOUS",
        "I'll connect you with someone from the team",
        "Sorry, I don’t have information",
    ):
        assert needle not in src
    assert owner_protocol_text("handoff", "en") == ""
    assert brain_template("no_evidence", "ar") == ""
    assert brain_template("faq_ambiguous", "fr") == ""


def test_no_greeting_templates_in_inbound_helper() -> None:
    greeting = (ROOT / "services/brain/inbound/text_handlers_message_greeting.py").read_text(encoding="utf-8")
    router = (ROOT / "services/brain/conversation_router.py").read_text(encoding="utf-8")
    assert "GREETING_TEMPLATES" not in greeting
    assert "GREETING_TEMPLATES" not in router
    assert "مرحباً! 😊" not in greeting
    assert "Hello! 😊 How can I help you today?" not in router


def test_appointment_slot_and_reminder_stay_absent() -> None:
    assert not (ROOT / "services/brain/appointment_slot_rules.py").exists()
    assert not (ROOT / "services/brain/reminder_analytics.py").exists()


def test_systemd_description_is_linas_ai_bot() -> None:
    unit = (ROOT / "deploy/systemd/linasbot.service").read_text(encoding="utf-8")
    assert "Description=Linas AI Bot" in unit
    assert "Laser" not in unit


def test_web_chat_default_greeting_is_owner_or_empty() -> None:
    assert default_greeting("ar") == ""
    assert default_greeting("en") == ""
    widget = SimpleNamespace(appearance={"identity": {"welcome_message": "Owner opener"}})
    assert default_greeting("en", widget) == "Owner opener"
    src = (ROOT / "services/integrations/web_chat/processor.py").read_text(encoding="utf-8")
    v2 = (ROOT / "services/integrations/web_chat/processor_v2_reply.py").read_text(encoding="utf-8")
    assert "safe_greeting_text" not in v2
    assert "brain_template" not in v2
    assert "كيف بقدر ساعدك" not in src


def test_safe_greeting_helper_has_no_canned_fallback() -> None:
    src = (ROOT / "services/brain/greeting.py").read_text(encoding="utf-8")
    assert "def safe_greeting_text" not in src
    assert "Hello! How can I help you today?" not in src
    assert "مرحباً! كيف يمكنني مساعدتك؟" not in src


@pytest.mark.asyncio
async def test_web_chat_v2_fail_and_leak_are_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.integrations.web_chat.processor_v2_reply import generate_web_chat_reply_text

    widget = SimpleNamespace(widget_key="w1")
    runtime = MagicMock()
    credit = MagicMock()

    async def boom(*_a, **_k):
        raise RuntimeError("terra down")

    monkeypatch.setattr(
        "services.integrations.web_chat.takeover_gate.maybe_silence_web_chat_for_takeover",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "services.integrations.web_chat.processor_v2_reply.fenced_failure_release",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "services.ai_setup.language_policy.detect_and_resolve_customer_languages",
        lambda **_k: {"detected_language": "en", "response_language": "en"},
    )
    monkeypatch.setattr("services.brain.reply.orchestrator.run_customer_reply_v2_dm", boom)
    with patch("services.integrations.web_chat.operation_heartbeat.OperationLeaseHeartbeat") as hb:
        hb.return_value.start = AsyncMock()
        hb.return_value.stop = AsyncMock()
        hb.return_value.lost_lease = False
        reply = await generate_web_chat_reply_text(
            tid="t1",
            text="hello",
            conversation_id="c1",
            widget=widget,
            visitor_id="v1",
            user_id="u1",
            word_notice=None,
            reply_precheck=SimpleNamespace(allowed=True),
            credit=credit,
            runtime=runtime,
        )
    assert reply == ""

    class _Out:
        reply = "Use this rule only if the user message is only a casual greeting."
        answer = None
        text = None
        reason = ""

    monkeypatch.setattr("services.brain.reply.orchestrator.run_customer_reply_v2_dm", AsyncMock(return_value=_Out()))
    with patch("services.integrations.web_chat.operation_heartbeat.OperationLeaseHeartbeat") as hb:
        hb.return_value.start = AsyncMock()
        hb.return_value.stop = AsyncMock()
        hb.return_value.lost_lease = False
        leaked = await generate_web_chat_reply_text(
            tid="t1",
            text="hello",
            conversation_id="c1",
            widget=widget,
            visitor_id="v1",
            user_id="u1",
            word_notice=None,
            reply_precheck=SimpleNamespace(allowed=True),
            credit=credit,
            runtime=runtime,
        )
    assert leaked == ""


@pytest.mark.asyncio
async def test_unanswered_handoff_sends_owner_protocol_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.agent.no_evidence_handoff import unanswered_question_result
    from services.brain.contracts.actions import ActionReceipt, ActionReceiptSet
    from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
    from services.brain.contracts.turn import CustomerTurn, HistorySnapshot

    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.human_handoff_enabled", lambda _tid: True)
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.execute_actions",
        AsyncMock(
            return_value=ActionReceiptSet(
                receipts=[
                    ActionReceipt(
                        action_id="handoff:unanswered",
                        action_type="escalate_to_human",
                        state="success",
                        backend_id="c-1",
                    )
                ]
            )
        ),
    )
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.owner_protocol_text",
        lambda *_a, **_k: "Owner handoff verbatim.",
    )
    result = await unanswered_question_result(
        CustomerTurn(
            tenant_id="t1",
            customer_id="u1",
            conversation_id="c1",
            channel="instagram_dm",
            extra={"response_language": "en"},
            history=HistorySnapshot(),
        ),
        message="What is your unpublished refund policy?",
        plan=PlannerPlan(
            tasks=[PlannerTask(id="t1", type="information", span=TaskSpan(text="policy?"))], read_only=True
        ),
        dest="dm",
        lang="en",
        extra={},
        agent_trace=[],
        outcome="not_found",
        evidence=[],
        structured_facts={},
        resource_receipts=[],
        visual_reason="",
        tool_rows=[],
    )
    assert result is not None
    assert result.envelope.messages[0].text == "Owner handoff verbatim."
    assert (result.extra or {}).get("customer_silence") is not True
