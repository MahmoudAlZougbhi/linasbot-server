"""Mixed hours/handoff/request turns must not swallow published answers."""

from __future__ import annotations

import pytest

from services.customer_ai.agent.action_gate import apply_action_gate
from services.customer_ai.contracts.actions import ActionReceipt
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.planner.heuristic import overlay_plan, plan_message


@pytest.mark.asyncio
async def test_mixed_human_and_hours_continues_to_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "شو ساعات أنطلياس وبدي احكي مع حدا"
    plan = plan_message(message)
    types = {task.type for task in plan.tasks}
    assert "hours" in types
    assert "human_request" in types

    async def fake_escalate(**_k):
        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    monkeypatch.setattr("services.customer_ai.actions.execute.escalate_to_human", fake_escalate)
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
    assert gated.extra.get("handoff_ok") is True
    assert gated.extra.get("handoff_receipts")


@pytest.mark.asyncio
async def test_human_only_still_stops_at_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_message("بدي احكي مع حدا")
    assert {task.type for task in plan.tasks} == {"human_request"}

    async def fake_escalate(**_k):
        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    monkeypatch.setattr("services.customer_ai.actions.execute.escalate_to_human", fake_escalate)
    turn = CustomerTurn(tenant_id="brain-shop", customer_id="u1", conversation_id="c-h", event_ids=["m2"])
    gated = await apply_action_gate(
        turn,
        plan,
        message="بدي احكي مع حدا",
        dest="instagram_dm:u1",
        lang="ar",
        extra={},
        agent_trace=[],
    )
    assert gated.early is not None
    assert gated.early.extra.get("phase") == "handoff"
    assert gated.early.envelope.decision == "handoff_ack"


def test_shop_b_rules_block_appointment_actions() -> None:
    message = "بدي موعد ليزر بكرا"
    blocked = overlay_plan(None, message, enabled_action_types={"product_request"})
    types = {task.type for task in blocked.tasks}
    assert "service_request" not in types
    allowed = overlay_plan(None, message, enabled_action_types={"service_request", "product_request", "human_request"})
    assert any(task.type == "service_request" for task in allowed.tasks)


def test_link_and_video_paraphrases_are_resource_requests() -> None:
    for message in (
        "ابعتلي رابط الحجز",
        "send me the booking link",
        "فرجيني فيديو الجلسة",
        "send the laser video please",
    ):
        types = {task.type for task in plan_message(message).tasks}
        assert "resource_request" in types, message
