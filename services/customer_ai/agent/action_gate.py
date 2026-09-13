"""Request/handoff holds. Mixed info+action must still retrieve and answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.customer_ai.actions.pending import attach_confirmation
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.stage_timeline import stamp
from services.customer_ai.templates import brain_template

_INFO_TYPES = {"information", "hours", "comparison"}
_CONTINUE_TYPES = _INFO_TYPES | {"resource_request", "service_request", "product_request", "cancel_or_status"}
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
    if not extra.get("handoff_ok"):
        return envelope
    text = brain_template("handoff", lang)
    if any((item.text or "").strip() == text for item in envelope.messages):
        return envelope
    return envelope.model_copy(
        update={"messages": [*list(envelope.messages), OutboundMessage(destination=dest, text=text, protected=True)]}
    )


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
    from services.customer_ai.actions.request_fields import published_request_fields

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
    from services.customer_ai.planner.published_rules import allowed_action_task_types

    return allowed_action_task_types(tenant_id)


def _should_continue(plan: PlannerPlan) -> bool:
    return any(task.type in _CONTINUE_TYPES for task in plan.tasks)


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
    extra = dict(extra)
    human = human_proposals(plan, tenant_id=turn.tenant_id)
    if human.actions:
        from services.customer_ai.actions.execute import execute_actions

        receipts = await execute_actions(turn=turn, proposals=human, customer_text=message)
        ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
        dumped = [item.model_dump() for item in receipts.receipts]
        extra["handoff_ok"] = ok
        extra["handoff_receipts"] = dumped
        extra["receipts"] = list(extra.get("receipts") or []) + dumped
        if not _should_continue(plan):
            agent_trace.append({"step": "FINAL", "decision": "handoff_ack" if ok else "no_reply"})
            envelope = FinalReplyEnvelope(
                decision="handoff_ack" if ok else "no_reply",
                messages=[OutboundMessage(destination=dest, text=brain_template("handoff", lang))] if ok else [],
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

    proposals = request_proposals(plan, tenant_id=turn.tenant_id)
    if proposals.actions:
        held = attach_confirmation(turn, proposals)
        extra = {
            **extra,
            "awaiting_confirmation": True,
            "pending_actions": [item.model_dump() for item in held.actions],
        }
        info_tasks = [task for task in plan.tasks if task.type in _INFO_TYPES]
        if not info_tasks:
            agent_trace.append({"step": "FINAL", "decision": "clarify", "reason": "awaiting_confirmation"})
            envelope = FinalReplyEnvelope(
                decision="clarify",
                messages=[OutboundMessage(destination=dest, text=brain_template("confirm_request", lang))],
            )
            envelope = append_handoff_message(envelope, extra, dest=dest, lang=lang)
            return ActionGateResult(
                early=TurnResult(
                    stop_reason="ok",
                    envelope=envelope,
                    extra=_flow_extra(
                        {
                            "phase": "actions_pending",
                            "plan": plan.model_dump(),
                            "awaiting_confirmation": True,
                            "pending_actions": [item.model_dump() for item in held.actions],
                            "agent_trace": agent_trace,
                            **extra,
                        },
                        ("request", "Waiting for customer confirmation before submitting request", None),
                    ),
                ),
                extra=extra,
            )
    return ActionGateResult(early=None, extra=extra)
