"""Terra-only customer replies: retrieve → Terra → outbound safety; silence on failure."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn, HistorySnapshot
from services.brain.outbound_safety import looks_like_instruction_text

ROOT = Path(__file__).resolve().parents[1]
_SOP = "Use this rule only if the user message is only a casual greeting."


def _turn() -> CustomerTurn:
    return CustomerTurn(
        tenant_id="t-terra-only",
        conversation_id="c1",
        channel="instagram_dm",
        history=HistorySnapshot(),
        extra={"response_language": "en"},
    )


@pytest.mark.asyncio
async def test_hello_goes_to_agentic_terra_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    called: dict[str, str] = {}

    async def agentic(turn, *, message, channel, flow_base, visual_reason):
        called["message"] = message
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="Hello from Terra")],
            ),
            ai_called=True,
            extra={"path": "agentic"},
        )

    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", AsyncMock(return_value=None))
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", agentic)
    out = await run_dm_after_gates(_turn(), message="Hello", channel="instagram_dm")
    assert called["message"] == "Hello"
    assert out.envelope.messages[0].text == "Hello from Terra"
    assert out.ai_called is True


@pytest.mark.asyncio
async def test_knowledge_question_retrieve_then_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.agent.generate_path import generate_verified

    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="knowledge:k1",
                source_family="knowledge",
                source_id="k1",
                title="Hours",
                text="We open at 10.",
            )
        ],
        outcome="found",
    )
    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information", span=TaskSpan(text="hours"))], read_only=True)

    async def terra(**_k):
        return FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="instagram_dm", text="We open at 10.")],
            used_evidence_ids=["knowledge:k1"],
        )

    monkeypatch.setattr("services.brain.agent.generate_path.openai_configured", lambda: True)
    monkeypatch.setattr("services.brain.agent.generate_path.load_identity_bundle", lambda _tid: object())
    monkeypatch.setattr("services.brain.agent.generate_path.generate_grounded_reply", terra)
    monkeypatch.setattr("services.brain.agent.generate_path.verify_answer", AsyncMock(return_value=type("V", (), {"verdict": "PASS", "unsupported_claims": [], "missing_tasks": [], "repair_instruction": ""})()))
    monkeypatch.setattr("services.brain.agent.generate_path.coverage_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("services.brain.agent.generate_path.apply_greeting", lambda t, m, c, e: e)
    monkeypatch.setattr(
        "services.brain.agent.action_gate.append_handoff_message",
        lambda env, extra, dest="", lang="": env,
    )
    out = await generate_verified(
        _turn(),
        message="What are your hours?",
        channel="instagram_dm",
        dest="instagram_dm",
        plan=plan,
        bundle=bundle,
        structured_facts={},
        visual_reason="",
        resource_receipts=[],
        tool_receipts=[],
        agent_trace=[],
        extra={},
        evidence=[],
    )
    assert out.stop_reason == "ok"
    assert out.envelope.messages[0].text == "We open at 10."
    assert out.ai_called is True


@pytest.mark.asyncio
async def test_terra_failure_is_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.agent.generate_path import generate_verified

    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information")], read_only=True)
    bundle = EvidenceBundle(items=[], outcome="found")
    monkeypatch.setattr("services.brain.agent.generate_path.openai_configured", lambda: True)
    monkeypatch.setattr("services.brain.agent.generate_path.load_identity_bundle", lambda _tid: object())
    monkeypatch.setattr("services.brain.agent.generate_path.generate_grounded_reply", AsyncMock(return_value=None))
    out = await generate_verified(
        _turn(),
        message="hours?",
        channel="instagram_dm",
        dest="instagram_dm",
        plan=plan,
        bundle=bundle,
        structured_facts={},
        visual_reason="",
        resource_receipts=[],
        tool_receipts=[],
        agent_trace=[],
        extra={},
        evidence=[],
    )
    assert out.stop_reason == "failed_closed"
    assert not out.envelope.messages
    assert (out.extra or {}).get("customer_silence") is True


@pytest.mark.asyncio
async def test_retrieve_miss_without_handoff_is_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.agent.no_evidence_handoff import unanswered_question_result

    monkeypatch.setattr("services.brain.agent.no_evidence_handoff._handoff_allowed", lambda _tid: False)
    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information")], read_only=True)
    out = await unanswered_question_result(
        _turn(),
        message="what is the price of full body?",
        plan=plan,
        dest="instagram_dm",
        lang="en",
        extra={"handoff_ok": False},
        agent_trace=[],
        outcome="not_found",
        evidence=[],
        structured_facts={},
        resource_receipts=[],
        visual_reason="",
        tool_rows=[],
    )
    assert out is not None
    assert not out.envelope.messages
    assert out.stop_reason == "failed_closed"


def test_outbound_safety_blocks_sop() -> None:
    from services.brain.runtime import _scrub_instruction_reply

    result = TurnResult(stop_reason="ok", envelope=FinalReplyEnvelope(decision="reply"))
    reply, extra = _scrub_instruction_reply(result, _SOP)
    assert looks_like_instruction_text(_SOP)
    assert reply is None
    assert extra.get("customer_silence") is True
    assert extra.get("outbound_instruction_blocked") is True


def test_luna_not_on_customer_inbound_modules() -> None:
    roots = (
        ROOT / "services/brain/reply",
        ROOT / "services/brain/inbound",
        ROOT / "services/brain/agent/loop.py",
        ROOT / "services/brain/runtime.py",
    )
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if "luna_chunker" in text or "apply_save_chunks" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_legacy_system_prompt_notes_are_not_indexed_prose() -> None:
    from services.brain.compiler.prose import extract_prose

    prose = extract_prose(
        "ai_basics",
        {
            "advanced_instructions": "Owner business hours policy for customers.",
            "notes": "INTERNAL_LEGACY_SYSTEM_PROMPT hash=abc Full prompt body retained.",
        },
    )
    assert "Owner business hours policy" in prose
    assert "INTERNAL_LEGACY_SYSTEM_PROMPT" not in prose
    assert "Full prompt body retained" not in prose


def test_live_cert_not_imported_by_production_entry() -> None:
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    worker = (ROOT / "worker.py").read_text(encoding="utf-8") if (ROOT / "worker.py").exists() else ""
    assert "_live_cert" not in main
    assert "_live_cert" not in worker
    assert (ROOT / "_live_cert" / "README.md").is_file()
