"""Action tools wrapping existing Customer Brain actions.execute / handoff / pending."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.execute import execute_actions
from services.customer_ai.actions.pending import attach_confirmation
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.turn import CustomerTurn

_ACTION_MAP = {
    "escalate_to_human": "escalate_to_human",
    "start_request": "start_request",
    "update_request_draft": "update_draft",
    "submit_request": "submit_request",
    "cancel_request": "cancel_request",
    "send_resource": "send_resource",
}


async def run_action(name: str, args: dict[str, Any], turn: CustomerTurn) -> dict[str, Any]:
    action_type = _ACTION_MAP.get(name)
    if not action_type:
        return {"ok": False, "error": "unknown_tool", "data": None}
    task_id = str(args.get("task_id") or "tool")
    fields = dict(args.get("fields") or {})
    for key in ("request_type", "title", "resource_id", "draft_id", "request_id"):
        if key in args and key not in fields:
            fields[key] = args[key]
    proposal = ActionProposal(task_id=task_id, action_type=action_type, fields=fields)  # type: ignore[arg-type]
    proposals = ActionProposalSet(actions=[proposal])
    if action_type in {"start_request", "submit_request"} and not args.get("confirmed"):
        pending = attach_confirmation(turn, proposals)
        return {
            "ok": True,
            "data": {"awaiting_confirmation": True, "pending_actions": [a.model_dump() for a in pending.actions]},
            "receipt": None,
        }
    receipts = await execute_actions(
        turn=turn,
        proposals=proposals,
        customer_text=str(args.get("customer_text") or args.get("text") or ""),
        session=args.get("session"),
    )
    receipt = receipts.receipts[0] if receipts.receipts else None
    ok = bool(receipt and receipt.state == "success")
    return {
        "ok": ok,
        "data": receipt.model_dump() if receipt else None,
        "receipt": receipt.model_dump() if receipt else None,
        "error": None if ok else (receipt.reason if receipt else "action_failed"),
    }


run_action_tool = run_action
