"""Mixed hours/handoff/request turns must not swallow published answers."""

from __future__ import annotations

import pytest

from services.brain.agent.action_gate import apply_action_gate
from services.brain.contracts.actions import ActionReceipt
from services.brain.contracts.turn import CustomerTurn
from services.brain.planner.heuristic import overlay_plan
from tests.plan_builders import explicit_plan


@pytest.mark.asyncio
async def test_mixed_human_and_hours_continues_to_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "شو ساعات أنطلياس وبدي احكي مع حدا"
    plan = explicit_plan(message, ("hours", ["hours", "branches"]), ("human_request", ["none"]))
    types = {task.type for task in plan.tasks}
    assert "hours" in types
    assert "human_request" in types

    async def fake_escalate(**_k):
        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    monkeypatch.setattr("services.brain.actions.execute.escalate_to_human", fake_escalate)
    turn = CustomerTurn(tenant_id="brain-shop", customer_id="u1", conversation_id="c-mix", event_ids=["m1"])
    gated = await apply_action_gate(
        turn,
        plan,
        message=message,
        dest="instagram_dm:u1",
        lang="ar",
        extra={},
        agent_trace=[],
    )
    assert gated.early is None
    assert gated.extra.get("pending_human_escalate") is True
    assert gated.extra.get("handoff_ok") is not True
    assert not gated.extra.get("handoff_receipts")


@pytest.mark.asyncio
async def test_human_only_still_stops_at_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "بدي احكي مع حدا"
    plan = explicit_plan(message, ("human_request", ["none"]))
    assert {task.type for task in plan.tasks} == {"human_request"}

    async def fake_escalate(**_k):
        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    monkeypatch.setattr("services.brain.actions.execute.escalate_to_human", fake_escalate)
    turn = CustomerTurn(tenant_id="brain-shop", customer_id="u1", conversation_id="c-h", event_ids=["m2"])
    gated = await apply_action_gate(
        turn,
        plan,
        message=message,
        dest="instagram_dm:u1",
        lang="ar",
        extra={},
        agent_trace=[],
    )
    assert gated.early is not None
    assert gated.early.extra.get("phase") == "handoff"
    assert gated.early.envelope.decision == "handoff_ack"
    assert gated.early.envelope.messages == []


def test_shop_b_rules_block_appointment_actions() -> None:
    message = "بدي موعد ليزر بكرا"
    llm = explicit_plan(message, ("service_request", ["services", "branches"]))
    blocked = overlay_plan(llm, message, enabled_action_types={"product_request"})
    types = {task.type for task in blocked.tasks}
    assert "service_request" not in types
    allowed = overlay_plan(llm, message, enabled_action_types={"service_request", "product_request", "human_request"})
    assert any(task.type == "service_request" for task in allowed.tasks)
