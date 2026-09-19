"""Action tools wrapping existing Customer Brain actions.execute / handoff / pending."""

from __future__ import annotations

from typing import Any

from services.brain.actions.execute import execute_actions
from services.brain.actions.pending import attach_confirmation
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.turn import CustomerTurn

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
    for key in (
        "request_type",
        "title",
        "resource_id",
        "resource_ref",
        "resource_ids",
        "kind",
        "allowed_source_ids",
        "draft_id",
        "request_id",
    ):
        if key in args and key not in fields:
            fields[key] = args[key]
    target_id = str(
        args.get("target_id")
        or args.get("resource_id")
        or args.get("resource_ref")
        or fields.get("resource_id")
        or fields.get("resource_ref")
        or ""
    )
    proposal = ActionProposal(
        task_id=task_id,
        action_type=action_type,  # type: ignore[arg-type]
        target_id=target_id,
        fields=fields,
    )
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
    ok = bool(receipt and receipt.state in {"success", "pending"})
    data: dict[str, Any] | None = receipt.model_dump() if receipt else None
    if action_type == "send_resource" and receipt is not None:
        from services.brain.tools.resource_delivery import attach_send_to_turn

        data = attach_send_to_turn(turn, receipt, session=args.get("session"))
        ok = bool(data.get("queued") or receipt.state in {"success", "pending"})
    return {
        "ok": ok,
        "data": data,
        "receipt": data,
        "error": None if ok else (receipt.reason if receipt else "action_failed"),
    }


run_action_tool = run_action
