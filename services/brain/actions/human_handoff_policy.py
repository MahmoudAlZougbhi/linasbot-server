"""HUMAN Live Chat handoff: Terra may speak, then escalate_to_human.

Hints from published HUMAN rules are model POLICY, never system-sent templates.
HUMAN never creates a Requests board card.
"""

from __future__ import annotations

from typing import Any

from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import TurnResult
from services.brain.contracts.turn import CustomerTurn

_CONTINUE_TYPES = {
    "information",
    "hours",
    "comparison",
    "resource_request",
    "service_request",
    "product_request",
    "cancel_or_status",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def enabled_human_rules(tenant_id: str) -> list[dict[str, Any]]:
    if not (tenant_id or "").strip():
        return []
    try:
        from services.brain.planner.published_rules import published_requests_payload
    except Exception:
        return []
    payload = published_requests_payload(tenant_id)
    rows: list[dict[str, Any]] = []
    for raw in payload.get("rules") or []:
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        if _text(raw.get("type")).upper() != "HUMAN":
            continue
        rows.append(raw)
    return rows


def pre_handoff_hint(tenant_id: str) -> str:
    """Owner hint for a short Terra line before escalate. Empty = silence is OK."""
    for rule in enabled_human_rules(tenant_id):
        for key in ("pre_handoff_message_hint", "handoff_guidance", "notes"):
            hint = _text(rule.get(key))
            if hint:
                return hint
    return ""


def has_human_task(plan: PlannerPlan) -> bool:
    return any(task.type == "human_request" for task in plan.tasks)


def has_continue_task(plan: PlannerPlan) -> bool:
    return any(task.type in _CONTINUE_TYPES for task in plan.tasks)


def speak_before_escalate(plan: PlannerPlan, hint: str) -> bool:
    if not has_human_task(plan):
        return False
    if has_continue_task(plan):
        return True
    return bool(_text(hint))


def allow_policy_only_generate(extra: dict[str, Any] | None) -> bool:
    row = extra or {}
    return bool(row.get("pending_human_escalate") or row.get("comment_invite_dm"))


def human_policy_notes(
    turn: CustomerTurn,
    plan: PlannerPlan | None = None,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    blob = extra if extra is not None else (turn.extra or {})
    hint = _text(blob.get("human_pre_handoff_hint")) or pre_handoff_hint(turn.tenant_id)
    if not hint and not blob.get("pending_human_escalate"):
        return []
    notes = [
        "HUMAN handoff is Live Chat only. Do not create a Requests board card. "
        "Do not claim a teammate already answered. Do not paste a protocol."
    ]
    if hint:
        notes.append(
            "Owner pre-handoff hint (write one short customer line in this spirit, then the "
            f"system will run escalate_to_human): {hint[:800]}"
        )
    if plan is not None and has_continue_task(plan):
        notes.append("Answer the customer's other questions in the same message, then one short handoff line.")
    return notes


def policy_receipts(extra: dict[str, Any] | None) -> list[str]:
    row = extra or {}
    out: list[str] = []
    if row.get("pending_human_escalate"):
        out.append("policy:human_pre_handoff")
    if row.get("comment_invite_dm"):
        out.append("policy:comment_invite_dm")
    return out


def bind_handoff_extra(turn: CustomerTurn, extra: dict[str, Any]) -> None:
    patch: dict[str, Any] = {}
    for key in ("pending_human_escalate", "human_pre_handoff_hint", "comment_invite_dm"):
        if extra.get(key):
            patch[key] = extra[key]
    if patch:
        turn.extra = {**(turn.extra or {}), **patch}


async def commit_pending_human_escalate(
    *,
    turn: CustomerTurn,
    plan: PlannerPlan,
    extra: dict[str, Any],
    result: TurnResult | None,
    message: str,
) -> TurnResult:
    if result is None:
        return TurnResult(stop_reason="failed_closed")
    merged = {**extra, **(result.extra or {})}
    if not merged.get("pending_human_escalate") or merged.get("handoff_ok"):
        return result
    from services.brain.actions.execute import execute_actions
    from services.brain.agent.action_gate import human_proposals
    from services.brain.stage_timeline import stamp

    receipts = await execute_actions(
        turn=turn, proposals=human_proposals(plan, tenant_id=turn.tenant_id), customer_text=message
    )
    ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
    dumped = [item.model_dump() for item in receipts.receipts]
    out_extra = dict(result.extra or extra)
    out_extra["handoff_ok"] = ok
    out_extra["handoff_receipts"] = dumped
    out_extra["pending_human_escalate"] = False
    out_extra["receipts"] = list(out_extra.get("receipts") or []) + dumped
    out_extra = stamp(
        out_extra,
        "handoff",
        title="Handed off to a human teammate",
        detail={"decision": "handoff_ack" if ok else "no_reply"},
    )
    envelope = result.envelope
    dispositions = dict(envelope.dispositions)
    dispositions["handoff"] = "action_succeeded" if ok else "failed"
    for task in plan.tasks:
        if task.type == "human_request":
            dispositions[task.id] = "action_succeeded" if ok else "failed"
    envelope = envelope.model_copy(update={"dispositions": dispositions})
    return result.model_copy(update={"envelope": envelope, "extra": out_extra})
