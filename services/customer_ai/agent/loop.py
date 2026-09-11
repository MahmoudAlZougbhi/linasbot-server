"""Bounded agentic Customer Brain turn: PLAN → RETRIEVE/TOOLS → OBSERVE → DECIDE → FINAL."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.pending import attach_confirmation
from services.customer_ai.agent.generate_path import generate_verified
from services.customer_ai.agent.multi_retrieve import multi_round_retrieve
from services.customer_ai.agent.rewrite import rewrite_queries
from services.customer_ai.agent.task_coverage import evaluate_task_coverage, missing_tasks
from services.customer_ai.billing import operation_id_for_turn, reserve_generative
from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.enums import StopReason
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.memory.store import recall_facts
from services.customer_ai.memory.summary import rolling_summary
from services.customer_ai.planner.openai_plan import plan_turn
from services.customer_ai.stage_timeline import StageTimer, evidence_preview, stamp
from services.customer_ai.templates import brain_template
from services.customer_ai.tools.registry import execute_tool


def _destination(channel: str) -> str:
    return "web_chat" if "web" in (channel or "") else "dm"


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def _history_blob(turn: CustomerTurn) -> str:
    visible = "\n".join(f"{item.role}: {item.text}" for item in turn.history.messages)
    older = rolling_summary(turn.history.messages, visible_cap=DEFAULT_BUDGETS.history_visible_cap)
    memory = recall_facts(
        tenant_id=turn.tenant_id,
        customer_id=turn.customer_id or "",
        limit=8,
    )
    mem_lines = [f"memory:{row.get('key')}={row.get('value')}" for row in memory if row.get("key")]
    parts = [p for p in (older, visible, "\n".join(mem_lines)) if p]
    return "\n".join(parts).strip()


def _stop_from_outcome(outcome: str) -> StopReason:
    if outcome in {
        "provider_not_configured",
        "index_not_ready",
        "product_index_stale",
        "unpublished",
        "context_overflow",
    }:
        return outcome  # type: ignore[return-value]
    if outcome == "source_unpublished":
        return "unpublished"
    return "failed_closed"


def _human_proposals(plan: PlannerPlan) -> ActionProposalSet:
    return ActionProposalSet(
        actions=[
            ActionProposal(task_id=task.id, action_type="escalate_to_human")
            for task in plan.tasks
            if task.type == "human_request"
        ]
    )


def _request_proposals(plan: PlannerPlan, *, tenant_id: str = "") -> ActionProposalSet:
    from services.customer_ai.actions.request_fields import published_request_fields

    actions = []
    for task in plan.tasks:
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


def _fast_path_eligible(plan: PlannerPlan) -> bool:
    info = [task for task in plan.tasks if task.type in {"information", "hours", "comparison"}]
    return plan.read_only and len(info) == 1 and all(t.type in {"information", "hours"} for t in info)


def _keep_generate_hold(result: TurnResult) -> bool:
    return result.stop_reason == "ok" and any((item.text or "").strip() for item in result.envelope.messages)


async def _maybe_tool_calls(
    turn: CustomerTurn,
    plan: PlannerPlan,
    message: str,
    *,
    budget: int,
    trace: list[dict[str, Any]],
    coverage: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], int]:
    from services.customer_ai.agent.tool_decide import propose_tools_dynamic
    from services.customer_ai.facts.structured import facts_from_tool_data

    receipts: list[str] = []
    tool_rows: list[dict[str, Any]] = []
    used = 0
    proposals = await propose_tools_dynamic(plan, message, coverage=coverage)
    for proposal in proposals:
        if used >= budget:
            trace.append({"step": "TOOL", "reason": "budget_exhausted", "tool_calls": used})
            break
        name = str(proposal.get("tool") or "")
        args = dict(proposal.get("args") or {})
        if not name:
            continue
        used += 1
        result = await execute_tool(name, args, turn)
        tool_rows.append(
            {
                "tool": name,
                "ok": result.get("ok"),
                "error": result.get("error"),
                "task_id": proposal.get("task_id"),
                "source": proposal.get("source"),
            }
        )
        trace.append(
            {
                "step": "TOOL",
                "tool": name,
                "ok": result.get("ok"),
                "task_id": proposal.get("task_id"),
                "source": proposal.get("source"),
            }
        )
        if result.get("receipt"):
            receipt = result["receipt"]
            receipts.append(
                f"{receipt.get('action_type')}:{receipt.get('state')}:{receipt.get('backend_id') or receipt.get('reason')}"
            )
        elif result.get("ok") and result.get("data") is not None:
            receipts.append(f"tool:{name}:ok")
            for fact in facts_from_tool_data(name, result.get("data"), tenant_id=turn.tenant_id, task_id=str(proposal.get("task_id") or "")):
                receipts.append(f"fact:{fact.kind}:{fact.entity_id}:{fact.value}")
    return tool_rows, receipts, used


async def run_agentic_turn(
    turn: CustomerTurn,
    message: str,
    channel: str,
    destination: str | None = None,
    *,
    plan: PlannerPlan | None = None,
    flow_extra: dict[str, Any] | None = None,
    visual_reason: str = "",
) -> TurnResult:
    dest = destination or _destination(channel)
    lang = _response_language(turn)
    agent_trace: list[dict[str, Any]] = []
    extra = dict(flow_extra or {})
    steps = 0
    max_steps = DEFAULT_BUDGETS.max_agent_steps
    tool_budget = DEFAULT_BUDGETS.max_tool_calls

    steps += 1
    agent_trace.append({"step": "PLAN", "n": steps})
    if plan is None:
        plan = await plan_turn(
            message,
            _history_blob(turn),
            tenant_id=turn.tenant_id,
            operation_id=operation_id_for_turn(turn),
        )
    extra = _flow_extra(
        extra,
        ("plan", "Understood the customer request", {"plan_tasks": [{"id": t.id, "type": t.type} for t in plan.tasks]}),
    )

    if any(task.type == "human_request" for task in plan.tasks):
        from services.customer_ai.actions.execute import execute_actions

        receipts = await execute_actions(turn=turn, proposals=_human_proposals(plan), customer_text=message)
        ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
        agent_trace.append({"step": "FINAL", "decision": "handoff_ack" if ok else "no_reply"})
        return TurnResult(
            stop_reason="ok" if ok else "failed_closed",
            envelope=FinalReplyEnvelope(
                decision="handoff_ack" if ok else "no_reply",
                messages=[OutboundMessage(destination=dest, text=brain_template("handoff", lang))] if ok else [],
                dispositions={"handoff": "action_succeeded" if ok else "failed"},
            ),
            extra=_flow_extra(
                {
                    "phase": "handoff",
                    "receipts": [r.model_dump() for r in receipts.receipts],
                    "agent_trace": agent_trace,
                    **extra,
                },
                ("handoff", "Handed off to a human teammate", {"decision": "handoff_ack" if ok else "no_reply"}),
            ),
        )

    request_proposals = _request_proposals(plan, tenant_id=turn.tenant_id)
    if request_proposals.actions:
        proposals = attach_confirmation(turn, request_proposals)
        agent_trace.append({"step": "FINAL", "decision": "clarify", "reason": "awaiting_confirmation"})
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="clarify",
                messages=[OutboundMessage(destination=dest, text=brain_template("confirm_request", lang))],
            ),
            extra=_flow_extra(
                {
                    "phase": "actions_pending",
                    "plan": plan.model_dump(),
                    "awaiting_confirmation": True,
                    "pending_actions": [item.model_dump() for item in proposals.actions],
                    "agent_trace": agent_trace,
                    **extra,
                },
                ("request", "Waiting for customer confirmation before submitting request", None),
            ),
        )

    steps += 1
    retrieve_timer = StageTimer()
    max_rounds = 1 if _fast_path_eligible(plan) else DEFAULT_BUDGETS.max_retrieval_rounds
    agent_trace.append({"step": "RETRIEVE", "n": steps, "max_rounds": max_rounds, "fast_path": max_rounds == 1})
    bundle, retrieve_trace, structured_facts = await multi_round_retrieve(
        turn, plan, message, max_rounds=max_rounds
    )
    agent_trace.extend({"step": "OBSERVE", **row} for row in retrieve_trace)
    evidence = evidence_preview(bundle)
    extra = _flow_extra(
        extra,
        (
            "search",
            "Searched published Knowledge / Services / Products / FAQ",
            {"ms": retrieve_timer.ms(), "retrieval_outcome": bundle.outcome, "evidence": evidence},
        ),
    )

    steps += 1
    tool_rows, tool_receipts, tools_used = await _maybe_tool_calls(
        turn, plan, message, budget=tool_budget, trace=agent_trace, coverage=evaluate_task_coverage(plan, bundle, structured_facts)
    )
    coverage = evaluate_task_coverage(plan, bundle, structured_facts)
    agent_trace.append({"step": "DECIDE", "n": steps, "tools_used": tools_used, "coverage": coverage})

    resource_receipts: list[dict] = []
    resource_result = None
    if any(task.type == "resource_request" for task in plan.tasks):
        from services.customer_ai.actions.resource_turn import resource_request_result

        evidence_ids = [item.source_id for item in bundle.items] + [item.evidence_id for item in bundle.items]
        resource_result = await resource_request_result(
            turn, message=message, channel=channel, plan=plan, evidence_source_ids=evidence_ids
        )
        info_tasks = [task for task in plan.tasks if task.type in {"information", "hours", "comparison"}]
        if resource_result is not None and not info_tasks:
            agent_trace.append({"step": "FINAL", "decision": "resource"})
            return resource_result.model_copy(
                update={
                    "extra": _flow_extra(
                        {
                            **(resource_result.extra or {}),
                            **extra,
                            "evidence_preview": evidence,
                            "agent_trace": agent_trace,
                        },
                        ("resource", "Prepared authorized resource to send", None),
                    )
                }
            )
        if resource_result is not None:
            resource_receipts = list((resource_result.extra or {}).get("receipts") or [])

    if bundle.outcome != "found":
        if resource_result is not None:
            return resource_result.model_copy(
                update={
                    "extra": {
                        **(resource_result.extra or {}),
                        **extra,
                        "evidence_preview": evidence,
                        "agent_trace": agent_trace,
                    }
                }
            )
        agent_trace.append({"step": "FINAL", "decision": "no_reply", "reason": bundle.outcome})
        return TurnResult(
            stop_reason=_stop_from_outcome(bundle.outcome),
            envelope=FinalReplyEnvelope(decision="no_reply"),
            extra=_flow_extra(
                {
                    "phase": "retrieve",
                    "retrieval_outcome": bundle.outcome,
                    "plan": plan.model_dump(),
                    "visual": visual_reason,
                    "receipts": resource_receipts,
                    "evidence_preview": evidence,
                    "agent_trace": agent_trace,
                    "structured_facts": structured_facts,
                    "tool_calls": tool_rows,
                    **extra,
                },
                ("search_empty", "No published evidence found for this question", {"retrieval_outcome": bundle.outcome}),
            ),
        )

    if missing_tasks(plan, coverage) and steps >= max_steps:
        agent_trace.append({"step": "FINAL", "decision": "clarify", "reason": "budget_exhausted_uncovered"})
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={
                "phase": "coverage",
                "plan": plan.model_dump(),
                "agent_trace": agent_trace,
                "structured_facts": structured_facts,
                "missing_tasks": missing_tasks(plan, coverage),
                **extra,
            },
        )

    held = reserve_generative(turn, mixed=any(item.source_family == "faq" for item in bundle.items))
    if held is not None:
        return held

    result: TurnResult | None = None
    try:
        result = await generate_verified(
            turn,
            message=message,
            channel=channel,
            dest=dest,
            plan=plan,
            bundle=bundle,
            structured_facts=structured_facts,
            visual_reason=visual_reason,
            resource_receipts=resource_receipts,
            tool_receipts=tool_receipts,
            agent_trace=agent_trace,
            extra=extra,
            evidence=evidence,
        )
        return result
    except Exception:
        from services.customer_ai.billing import release_turn_reservation

        release_turn_reservation(turn)
        raise
    finally:
        if result is not None and not _keep_generate_hold(result):
            from services.customer_ai.billing import release_turn_reservation

            release_turn_reservation(turn)


async def run_agentic_dm_path(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    flow_base: dict[str, Any] | None = None,
    visual_reason: str = "",
) -> TurnResult:
    from services.customer_ai.turn_pipeline import inbound_task_text

    task_text = inbound_task_text(turn, message)
    rewritten = await rewrite_queries(task_text, list(turn.history.messages), _response_language(turn))
    if rewritten.get("rewritten") and rewritten["rewritten"].strip() != task_text.strip():
        task_text = rewritten["rewritten"]
        flow_base = _flow_extra(
            flow_base,
            ("context", "Resolved follow-up using recent conversation", {"variants": rewritten.get("variants")}),
        )
    plan_timer = StageTimer()
    plan = await plan_turn(
        task_text,
        _history_blob(turn),
        tenant_id=turn.tenant_id,
        operation_id=operation_id_for_turn(turn),
    )
    flow_base = _flow_extra(
        flow_base,
        (
            "plan",
            "Understood the customer request",
            {"ms": plan_timer.ms(), "plan_tasks": [{"id": task.id, "type": task.type} for task in plan.tasks]},
        ),
    )
    return await run_agentic_turn(
        turn,
        task_text,
        channel,
        plan=plan,
        flow_extra=flow_base,
        visual_reason=visual_reason,
    )
