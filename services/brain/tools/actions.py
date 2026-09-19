"""Action tools wrapping existing Customer Brain actions.execute / handoff / pending."""

from __future__ import annotations

from typing import Any

from services.brain.actions.execute import execute_actions
from services.brain.actions.pending import attach_confirmation
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.turn import CustomerTurn
from services.brain.profile.store import remember_profile

_ACTION_MAP = {
    "escalate_to_human": "escalate_to_human",
    "start_request": "start_request",
    "update_request_draft": "update_draft",
    "submit_request": "submit_request",
    "cancel_request": "cancel_request",
    "send_resource": "send_resource",
}


def _persist_profile(turn: CustomerTurn, args: dict[str, Any]) -> None:
    raw_fields = args.get("fields")
    fields = dict(raw_fields) if isinstance(raw_fields, dict) else {}
    raw_collected = fields.get("collected_fields")
    collected = dict(raw_collected) if isinstance(raw_collected, dict) else {}
    for key in ("name", "customer_name", "gender", "age", "phone"):
        if key in args and str(args.get(key) or "").strip():
            collected[key] = args[key]
    request_type = str(args.get("request_type") or fields.get("request_type") or "").upper()
    required: set[str] = set()
    if request_type:
        from services.brain.agent.request_snapshot import build_request_snapshot, required_fields_for_type

        snap = build_request_snapshot(turn)
        required = set(required_fields_for_type(turn.tenant_id, request_type, list(snap.get("published_rules") or [])))
        required.update(str(item) for item in (snap.get("required_fields") or []) if str(item).strip())
    remember_profile(
        turn.tenant_id,
        turn.customer_id or "",
        collected,
        required=required,
        conversation_id=turn.conversation_id,
    )


async def run_action(name: str, args: dict[str, Any], turn: CustomerTurn) -> dict[str, Any]:
    if name == "no_request_action":
        return {"ok": True, "data": {"no_request_action": True}, "receipt": None}
    action_type = _ACTION_MAP.get(name)
    if not action_type:
        return {"ok": False, "error": "unknown_tool", "data": None}
    task_id = str(args.get("task_id") or "tool")
    fields = dict(args.get("fields") or {})
    for key in ("request_type", "title", "resource_id", "draft_id", "request_id"):
        if key in args and key not in fields:
            fields[key] = args[key]
    if name == "start_request" and str(fields.get("request_type") or "").upper() == "HUMAN":
        return {"ok": False, "error": "human_use_escalate_to_human", "data": None}
    proposal = ActionProposal(task_id=task_id, action_type=action_type, fields=fields)  # type: ignore[arg-type]
    proposals = ActionProposalSet(actions=[proposal])
    if action_type in {"start_request", "submit_request"} and not args.get("confirmed"):
        pending = attach_confirmation(turn, proposals)
        _persist_profile(turn, args)
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
    if name == "update_request_draft":
        _persist_profile(turn, args)
    receipt = receipts.receipts[0] if receipts.receipts else None
    ok = bool(receipt and receipt.state == "success")
    return {
        "ok": ok,
        "data": receipt.model_dump() if receipt else None,
        "receipt": receipt.model_dump() if receipt else None,
        "error": None if ok else (receipt.reason if receipt else "action_failed"),
    }


run_action_tool = run_action
