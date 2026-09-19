"""Resource-request turns: inventory is a read. Send only via send_resource."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.turn import CustomerTurn


async def resource_request_result(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    plan: PlannerPlan,
    evidence_source_ids: list[str] | None = None,
) -> None:
    """Comment surface does not auto-send catalog media. DM send is tool-only."""
    _ = (message, channel, plan, evidence_source_ids)
    if str(getattr(turn, "surface", "") or "") == "comment":
        return None
    return None


def resource_proposals(
    plan: PlannerPlan,
    *,
    tenant_id: str,
    query: str,
    evidence_source_ids: list[str] | None = None,
) -> ActionProposalSet:
    """No silent kind pick. send_resource needs an explicit id/kind from Terra."""
    _ = (tenant_id, query, evidence_source_ids)
    return ActionProposalSet(
        actions=[
            ActionProposal(task_id=task.id, action_type="send_resource", target_id="", fields={})
            for task in plan.tasks
            if task.type == "resource_request"
        ]
    )


async def execute_resource_proposals(
    turn: CustomerTurn,
    proposals: ActionProposalSet,
    *,
    customer_text: str,
) -> list[dict[str, Any]]:
    from services.brain.actions.execute import execute_actions

    receipts = await execute_actions(turn=turn, proposals=proposals, customer_text=customer_text)
    return [item.model_dump() for item in receipts.receipts]
