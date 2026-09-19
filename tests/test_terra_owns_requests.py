"""Freeze: customer DM agentic path does not call a separate planner."""

from __future__ import annotations

from inspect import getsource
from pathlib import Path

import pytest

from services.brain.agent import loop as agent_loop
from services.brain.agent.default_plan import default_agentic_plan
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.tools.registry import execute_tool
from services.brain.turn_pipeline import run_dm_after_gates


def test_loop_source_has_no_plan_turn() -> None:
    text = Path(agent_loop.__file__).read_text(encoding="utf-8")
    assert "plan_turn" not in text
    assert "openai_plan" not in text
    assert "run_terra_request_round" in text
    assert "default_agentic_plan" in getsource(agent_loop.run_agentic_dm_path)


def test_default_agentic_plan_searches_cm_together() -> None:
    plan = default_agentic_plan("hours and prices please")
    families = set(plan.tasks[0].source_families)
    for name in ("knowledge", "care", "faq", "hours", "services", "prices", "products"):
        assert name in families
    assert {task.type for task in plan.tasks} == {"information"}


@pytest.mark.asyncio
async def test_agentic_dm_does_not_call_plan_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"plan": 0}

    async def boom(*_a, **_k):
        called["plan"] += 1
        raise AssertionError("plan_turn must not run on DM agentic")

    async def found_retrieve(*_a, **_k):
        return (
            EvidenceBundle(
                outcome="found",
                items=[
                    EvidenceItem(
                        evidence_id="k1",
                        source_family="knowledge",
                        source_id="k1",
                        title="Info",
                        text="Published fact.",
                    )
                ],
            ),
            [],
            {},
        )

    async def fake_generate(turn, **_k):
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="ok")],
            ),
            extra=dict(turn.extra or {}),
        )

    async def idle_terra(*_a, **_k):
        return [], [], 0, {"request_state": {"module_enabled": False}}

    monkeypatch.setattr("services.brain.planner.openai_plan.plan_turn", boom)
    monkeypatch.setattr("services.brain.planner.openai_plan.plan_with_openai", boom)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.generate_verified", fake_generate)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_request_round", idle_terra)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_sem)
    turn = CustomerTurn(tenant_id="t-freeze", conversation_id="c1", event_ids=["m1"], channel="whatsapp")
    result = await run_dm_after_gates(turn, message="how much is laser?", channel="whatsapp")
    assert called["plan"] == 0
    assert result.envelope.decision == "reply"


@pytest.mark.asyncio
async def test_start_request_and_human_tool_contract() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"], customer_id="u1")
    human = await execute_tool("start_request", {"request_type": "HUMAN", "title": "help"}, turn)
    assert human.get("ok") is False
    assert human.get("error") == "human_use_escalate_to_human"
    idle = await execute_tool("no_request_action", {}, turn)
    assert idle.get("ok") is True
    started = await execute_tool("start_request", {"request_type": "ORDER", "title": "kit"}, turn)
    assert started.get("ok") is True
    assert (started.get("data") or {}).get("awaiting_confirmation") is True
