"""Request/handoff holds. Mixed info+action must still retrieve and answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.brain.actions.human_handoff_policy import (
    bind_handoff_extra,
    has_human_task,
    pre_handoff_hint,
    speak_before_escalate,
)
from services.brain.actions.pending import attach_confirmation
from services.brain.comments.public_request_policy import comment_has_public_request, skip_comment_request_staging
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.stage_timeline import stamp

_RULE_BOUND = {"human_request", "service_request", "product_request"}


@dataclass
class ActionGateResult:
    early: TurnResult | None
    extra: dict[str, Any]


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def append_handoff_message(
    envelope: FinalReplyEnvelope,
    extra: dict[str, Any],
    *,
    dest: str,
    lang: str,
) -> FinalReplyEnvelope:
    """Handoff is Live Chat only. Terra/silence owns customer copy — never append protocol text."""
    _ = (extra, dest, lang)
    return envelope


def human_proposals(plan: PlannerPlan, *, tenant_id: str = "") -> ActionProposalSet:
    allowed = _allowed_actions(tenant_id)
    if allowed is not None and "human_request" not in allowed:
        return ActionProposalSet(actions=[])
    return ActionProposalSet(
        actions=[
            ActionProposal(task_id=task.id, action_type="escalate_to_human")
            for task in plan.tasks
            if task.type == "human_request"
        ]
    )


def request_proposals(plan: PlannerPlan, *, tenant_id: str = "") -> ActionProposalSet:
    from services.brain.actions.request_fields import published_request_fields

    allowed = _allowed_actions(tenant_id)
    actions = []
    for task in plan.tasks:
        if allowed is not None and task.type in _RULE_BOUND and task.type not in allowed:
            continue
        if task.type == "service_request":
            kind = "APPOINTMENT"
        elif task.type == "product_request":
            kind = "ORDER"
        elif task.type == "cancel_or_status":
            actions.append(ActionProposal(task_id=task.id, action_type="cancel_request"))
            continue
        else:
            continue
        fields = {"request_type": kind, "title": task.span.text[:80], **published_request_fields(tenant_id, kind)}
        actions.append(ActionProposal(task_id=task.id, action_type="start_request", fields=fields))
    return ActionProposalSet(actions=actions)


def _allowed_actions(tenant_id: str) -> set[str] | None:
    if not (tenant_id or "").strip():
        return None
    from services.brain.planner.published_rules import allowed_action_task_types

    return allowed_action_task_types(tenant_id)


async def _silence_escalate(
    turn: CustomerTurn,
    plan: PlannerPlan,
    *,
    message: str,
    extra: dict[str, Any],
    agent_trace: list[dict[str, Any]],
) -> ActionGateResult:
    from services.brain.actions.execute import execute_actions

    human = human_proposals(plan, tenant_id=turn.tenant_id)
    receipts = await execute_actions(turn=turn, proposals=human, customer_text=message)
    ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
    dumped = [item.model_dump() for item in receipts.receipts]
    extra["handoff_ok"] = ok
    extra["handoff_receipts"] = dumped
    extra["receipts"] = list(extra.get("receipts") or []) + dumped
    agent_trace.append({"step": "FINAL", "decision": "handoff_ack" if ok else "no_reply"})
    envelope = FinalReplyEnvelope(
        decision="handoff_ack" if ok else "no_reply",
        messages=[],
        dispositions={"handoff": "action_succeeded" if ok else "failed"},
    )
    return ActionGateResult(
        early=TurnResult(
            stop_reason="ok" if ok else "failed_closed",
            envelope=envelope,
            extra=_flow_extra(
                {
                    "phase": "handoff",
                    "receipts": dumped,
                    "agent_trace": agent_trace,
                    **extra,
                },
                (
                    "handoff",
                    "Handed off to a human teammate",
                    {"decision": "handoff_ack" if ok else "no_reply"},
                ),
            ),
        ),
        extra=extra,
    )


async def apply_action_gate(
    turn: CustomerTurn,
    plan: PlannerPlan,
    *,
    message: str,
    dest: str,
    lang: str,
    extra: dict[str, Any],
    agent_trace: list[dict[str, Any]],
) -> ActionGateResult:
    _ = (dest, lang)
    extra = dict(extra)
    if has_human_task(plan):
        hint = pre_handoff_hint(turn.tenant_id)
        extra["human_pre_handoff_hint"] = hint
        if speak_before_escalate(plan, hint):
            extra["pending_human_escalate"] = True
            bind_handoff_extra(turn, extra)
        else:
            return await _silence_escalate(turn, plan, message=message, extra=extra, agent_trace=agent_trace)

    if comment_has_public_request(turn, plan):
        extra["comment_invite_dm"] = True
        bind_handoff_extra(turn, extra)

    if not skip_comment_request_staging(turn):
        proposals = request_proposals(plan, tenant_id=turn.tenant_id)
        if proposals.actions:
            held = attach_confirmation(turn, proposals)
            extra = {
                **extra,
                "awaiting_confirmation": True,
                "pending_actions": [item.model_dump() for item in held.actions],
            }
    return ActionGateResult(early=None, extra=extra)
