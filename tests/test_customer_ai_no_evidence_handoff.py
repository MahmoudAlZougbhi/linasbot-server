"""Unanswered published-info questions go to Live Chat. Small talk does not."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.brain.agent.action_gate import ActionGateResult
from services.brain.agent.loop import run_agentic_turn
from services.brain.agent.no_evidence_handoff import should_handoff_unanswered, unanswered_question_result
from services.brain.contracts.actions import ActionReceipt, ActionReceiptSet
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.contracts.turn import CustomerTurn, HistorySnapshot
from services.brain.templates import brain_template, owner_protocol_text


def _plan(*tasks: PlannerTask) -> PlannerPlan:
    return PlannerPlan(tasks=list(tasks), read_only=True)


def _task(
    task_id: str,
    task_type: str = "information",
    *,
    families: list[str] | None = None,
    span: str = "",
) -> PlannerTask:
    return PlannerTask(
        id=task_id,
        type=task_type,  # type: ignore[arg-type]
        span=TaskSpan(text=span or task_id),
        source_families=list(families or ["knowledge"]),  # type: ignore[arg-type]
    )


def _turn(*, kind: str = "dm", lang: str = "en") -> CustomerTurn:
    comment = kind == "comment"
    return CustomerTurn(
        tenant_id="t-unanswered",
        customer_id="u-1",
        conversation_id="c-1",
        channel="instagram_comment" if comment else "instagram_dm",
        surface="comment" if comment else "dm",
        invocation_kind=kind,  # type: ignore[arg-type]
        extra={"response_language": lang},
        history=HistorySnapshot(),
    )


def test_should_handoff_only_unanswered_questions() -> None:
    info = _plan(_task("t1", "information", span="guest wifi?"))
    hours = _plan(_task("h1", "hours", families=["hours", "branches"], span="antelias hours"))
    ack = _plan(_task("t1", "information", span="thanks"))
    found_hours = hours
    assert should_handoff_unanswered(plan=info, outcome="not_found", message="Do you have guest wifi?") is True
    assert should_handoff_unanswered(plan=hours, outcome="not_found", message="شو ساعات أنطلياس؟") is True
    assert should_handoff_unanswered(plan=found_hours, outcome="found", message="شو ساعات أنطلياس؟") is False
    assert should_handoff_unanswered(plan=hours, outcome="index_not_ready", message="شو ساعات أنطلياس؟") is False
    assert should_handoff_unanswered(plan=hours, outcome="ambiguous", message="شو ساعات أنطلياس؟") is False
    assert should_handoff_unanswered(plan=ack, outcome="not_found", message="thanks") is False
    assert (
        should_handoff_unanswered(
            plan=info, outcome="not_found", message="Do you have guest wifi?", invocation_kind="comment"
        )
        is True
    )
    catchall = _plan(
        _task("t1", "information", families=["knowledge", "care", "services", "faq", "branches"], span="ok")
    )
    assert should_handoff_unanswered(plan=catchall, outcome="not_found", message="ok") is False
    assert should_handoff_unanswered(plan=catchall, outcome="not_found", message="cool") is False
    assert should_handoff_unanswered(plan=info, outcome="not_found", message="عنوان") is True


def test_owner_protocol_empty_does_not_invent_handoff_copy() -> None:
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "services/brain/templates.py").read_text(encoding="utf-8")
    assert "_HANDOFF" not in src
    assert "_NO_EVIDENCE" not in src
    assert "I'll connect you with someone from the team" not in src
    assert "آسف، ما عندي معلومات" not in src
    assert owner_protocol_text("handoff", "en") == ""
    assert owner_protocol_text("no_evidence_handoff", "ar") == ""
    assert brain_template("handoff", "en") == ""
    assert brain_template("confirm_request", "en") == ""


@pytest.mark.asyncio
async def test_unanswered_question_persists_live_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.human_handoff_enabled",
        lambda _tid: True,
    )
    execute = AsyncMock(
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
    )
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.execute_actions", execute)
    plan = _plan(_task("t1", "information", span="unpublished policy?"))
    result = await unanswered_question_result(
        _turn(),
        message="What is your unpublished refund policy?",
        plan=plan,
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
    assert result.stop_reason == "ok"
    assert result.envelope.decision == "handoff_ack"
    assert not result.envelope.messages
    assert (result.extra or {}).get("customer_silence") is True
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_unanswered_does_not_claim_transfer_when_persist_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.human_handoff_enabled",
        lambda _tid: True,
    )
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.execute_actions",
        AsyncMock(
            return_value=ActionReceiptSet(
                receipts=[
                    ActionReceipt(
                        action_id="handoff:unanswered",
                        action_type="escalate_to_human",
                        state="failure",
                        reason="handoff_persist_failed",
                    )
                ]
            )
        ),
    )
    result = await unanswered_question_result(
        _turn(),
        message="What is your unpublished refund policy?",
        plan=_plan(_task("t1", "information", span="policy?")),
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
    assert result.envelope.decision == "clarify"
    assert not result.envelope.messages
    assert result.stop_reason == "failed_closed"


@pytest.mark.asyncio
async def test_agentic_not_found_question_hands_off(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gate(turn, plan, *, message, dest, lang, extra, agent_trace):
        return ActionGateResult(early=None, extra=dict(extra))

    async def _retrieve(*_a, **_k):
        return EvidenceBundle(items=[], outcome="not_found"), [], {}

    execute = AsyncMock(
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
    )
    monkeypatch.setattr("services.brain.agent.loop.apply_action_gate", _gate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _retrieve)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))
    monkeypatch.setattr(
        "services.brain.agent.no_evidence_handoff.human_handoff_enabled",
        lambda _tid: True,
    )
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.execute_actions", execute)
    result = await run_agentic_turn(
        _turn(),
        "What is your unpublished refund policy?",
        "instagram_dm",
        plan=_plan(_task("t1", "information", span="unpublished refund?")),
    )
    assert result.envelope.decision == "handoff_ack"
    assert result.stop_reason == "ok"
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_agentic_found_hours_does_not_auto_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gate(turn, plan, *, message, dest, lang, extra, agent_trace):
        return ActionGateResult(early=None, extra=dict(extra))

    async def _retrieve(*_a, **_k):
        item = EvidenceItem(
            evidence_id="hours:antelias",
            source_family="hours",
            source_id="antelias",
            title="Antelias",
            text="monday: 11:00–19:00",
        )
        return EvidenceBundle(items=[item], outcome="found"), [], {}

    execute = AsyncMock()

    async def _generate(*_a, **_k):
        from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult

        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="Antelias is open 11:00–19:00.")],
            ),
        )

    monkeypatch.setattr("services.brain.agent.loop.apply_action_gate", _gate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _retrieve)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))
    monkeypatch.setattr("services.brain.agent.loop.generate_verified", _generate)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.execute_actions", execute)
    result = await run_agentic_turn(
        _turn(),
        "شو ساعات أنطلياس؟",
        "instagram_dm",
        plan=_plan(_task("h1", "hours", families=["hours", "branches"], span="antelias")),
    )
    assert result.envelope.decision == "reply"
    assert "11:00" in result.envelope.messages[0].text
    execute.assert_not_called()


@pytest.mark.asyncio
async def test_index_not_ready_does_not_auto_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gate(turn, plan, *, message, dest, lang, extra, agent_trace):
        return ActionGateResult(early=None, extra=dict(extra))

    async def _retrieve(*_a, **_k):
        return EvidenceBundle(items=[], outcome="index_not_ready"), [], {}

    execute = AsyncMock()
    monkeypatch.setattr("services.brain.agent.loop.apply_action_gate", _gate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _retrieve)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.execute_actions", execute)
    result = await run_agentic_turn(
        _turn(),
        "What is your unpublished refund policy?",
        "instagram_dm",
        plan=_plan(_task("t1", "information", span="policy?")),
    )
    assert result.envelope.decision == "no_reply"
    assert result.stop_reason == "index_not_ready"
    execute.assert_not_called()


def test_comment_ack_and_emoji_are_small_talk() -> None:
    from services.brain.agent.no_evidence_handoff import is_comment_ack

    assert is_comment_ack("nice") is True
    assert is_comment_ack("🔥") is True
    assert is_comment_ack("WAW") is True
    assert is_comment_ack("Whats") is True
    assert is_comment_ack("hey") is True
    assert is_comment_ack("price?") is False
    assert is_comment_ack("عنوان") is False


@pytest.mark.asyncio
async def test_comment_ack_replies_when_retrieve_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gate(turn, plan, *, message, dest, lang, extra, agent_trace):
        return ActionGateResult(early=None, extra=dict(extra))

    async def _retrieve(*_a, **_k):
        return EvidenceBundle(items=[], outcome="not_found"), [], {}

    async def _greet(turn, *, message, channel, flow_base=None):
        from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult

        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="Thanks for commenting!")],
            ),
        )

    monkeypatch.setattr("services.brain.agent.loop.apply_action_gate", _gate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _retrieve)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))
    monkeypatch.setattr("services.brain.agent.greeting_turn.identity_greeting_result", _greet)
    result = await run_agentic_turn(
        _turn(kind="comment"),
        "nice",
        "instagram_comment",
        plan=_plan(_task("t1", "information", span="nice")),
    )
    assert result.stop_reason == "ok"
    assert result.envelope.messages[0].destination == "comment"
    assert "Thanks" in result.envelope.messages[0].text


@pytest.mark.asyncio
async def test_comment_question_hands_off_instead_of_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gate(turn, plan, *, message, dest, lang, extra, agent_trace):
        return ActionGateResult(early=None, extra=dict(extra))

    async def _retrieve(*_a, **_k):
        return EvidenceBundle(items=[], outcome="not_found"), [], {}

    execute = AsyncMock(
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
    )
    monkeypatch.setattr("services.brain.agent.loop.apply_action_gate", _gate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _retrieve)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.human_handoff_enabled", lambda _tid: True)
    monkeypatch.setattr("services.brain.agent.no_evidence_handoff.execute_actions", execute)
    result = await run_agentic_turn(
        _turn(kind="comment"),
        "What is the underarm price?",
        "instagram_comment",
        plan=_plan(_task("t1", "information", families=["prices", "services"], span="underarm")),
    )
    assert result.stop_reason == "ok"
    assert result.envelope.decision == "handoff_ack"
    execute.assert_awaited_once()
