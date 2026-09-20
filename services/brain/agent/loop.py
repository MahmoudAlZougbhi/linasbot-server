"""Bounded agentic Customer Brain turn: RETRIEVE → one Terra session (tools + reply)."""

from __future__ import annotations

from typing import Any

from services.brain.actions.human_handoff_policy import allow_policy_only_generate, commit_pending_human_escalate
from services.brain.agent.action_gate import apply_action_gate
from services.brain.agent.default_plan import default_agentic_plan, information_plan_for_comment
from services.brain.agent.multi_retrieve import multi_round_retrieve
from services.brain.agent.rewrite import rewrite_queries
from services.brain.agent.task_coverage import evaluate_task_coverage, missing_tasks
from services.brain.agent.terra_turn import run_terra_turn
from services.brain.billing import reserve_generative
from services.brain.budgets import budgets_for_tenant
from services.brain.contracts.enums import StopReason
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.stage_timeline import StageTimer, evidence_preview, stamp


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


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


def _fast_path_eligible(plan: PlannerPlan) -> bool:
    info = [task for task in plan.tasks if task.type in {"information", "hours", "comparison"}]
    return plan.read_only and len(info) == 1 and all(t.type in {"information", "hours"} for t in info)


def _keep_generate_hold(result: TurnResult) -> bool:
    return result.stop_reason == "ok" and any((item.text or "").strip() for item in result.envelope.messages)


def _ack_only(plan: PlannerPlan) -> bool:
    return bool(plan.tasks) and all(task.type == "acknowledgement" for task in plan.tasks)


async def _retrieve(
    turn: CustomerTurn,
    plan: PlannerPlan,
    message: str,
    extra: dict[str, Any],
    agent_trace: list[dict[str, Any]],
    steps: int,
) -> tuple[EvidenceBundle, dict[str, Any], list[dict[str, str]], dict[str, Any], int]:
    steps += 1
    retrieve_timer = StageTimer()
    max_rounds = 1 if _fast_path_eligible(plan) else budgets_for_tenant(turn.tenant_id).max_retrieval_rounds
    agent_trace.append({"step": "RETRIEVE", "n": steps, "max_rounds": max_rounds, "fast_path": max_rounds == 1})
    bundle, retrieve_trace, structured_facts = await multi_round_retrieve(turn, plan, message, max_rounds=max_rounds)
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
    extra["evidence_source_ids"] = [item.source_id for item in bundle.items] + [
        item.evidence_id for item in bundle.items
    ]
    turn.extra["evidence_source_ids"] = extra["evidence_source_ids"]
    return bundle, extra, evidence, structured_facts, steps


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
    dest = destination or _destination(channel, turn)
    lang = _response_language(turn)
    agent_trace: list[dict[str, Any]] = []
    extra = dict(flow_extra or {})
    steps = 0
    max_steps = budgets_for_tenant(turn.tenant_id).max_agent_steps

    steps += 1
    agent_trace.append({"step": "PLAN", "n": steps})
    if plan is None:
        plan = default_agentic_plan(message)
    if str(getattr(turn, "surface", "") or "") == "comment":
        from services.brain.planner.heuristic import planner_customer_text

        plan = information_plan_for_comment(plan, planner_customer_text(message))
    extra = _flow_extra(
        extra,
        ("plan", "Understood the customer request", {"plan_tasks": [{"id": t.id, "type": t.type} for t in plan.tasks]}),
    )

    gated = await apply_action_gate(
        turn,
        plan,
        message=message,
        dest=dest,
        lang=lang,
        extra=extra,
        agent_trace=agent_trace,
    )
    extra = gated.extra
    if gated.early is not None:
        return gated.early

    greeting_turn = _ack_only(plan)
    if greeting_turn:
        extra["identity_ok"] = True
        extra["retrieval_skipped"] = True
        bundle = EvidenceBundle(outcome="not_found")
        structured_facts: dict[str, Any] = {}
        evidence = evidence_preview(bundle)
    else:
        from services.brain.inbound.ack_then_reply import maybe_send_heavy_turn_ack

        await maybe_send_heavy_turn_ack(turn, message=message, channel=channel)
        bundle, extra, evidence, structured_facts, steps = await _retrieve(
            turn, plan, message, extra, agent_trace, steps
        )

    if bundle.outcome != "found" and not allow_policy_only_generate(extra) and not extra.get("identity_ok"):
        from services.brain.agent.handoff_policy import unanswered_question_result

        handed = await unanswered_question_result(
            turn,
            message=message,
            plan=plan,
            dest=dest,
            lang=lang,
            extra=extra,
            agent_trace=agent_trace,
            outcome=str(bundle.outcome),
            evidence=evidence,
            structured_facts=structured_facts,
            resource_receipts=[],
            visual_reason=visual_reason,
            tool_rows=[],
        )
        if handed is not None:
            return handed
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
                    "receipts": [],
                    "evidence_preview": evidence,
                    "agent_trace": agent_trace,
                    "structured_facts": structured_facts,
                    **extra,
                },
                (
                    "search_empty",
                    "No published evidence found for this question",
                    {"retrieval_outcome": bundle.outcome},
                ),
            ),
        )

    coverage = evaluate_task_coverage(plan, bundle, structured_facts)
    if missing_tasks(plan, coverage) and steps >= max_steps and not allow_policy_only_generate(extra):
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
        if extra.get("resource_delivery") or extra.get("resource_inventory"):
            held = held.model_copy(update={"extra": {**(held.extra or {}), **extra}})
        return held

    result: TurnResult | None = None
    try:
        result = await run_terra_turn(
            turn,
            message=message,
            channel=channel,
            dest=dest,
            plan=plan,
            bundle=bundle,
            structured_facts=structured_facts,
            visual_reason=visual_reason,
            extra=extra,
            evidence=evidence,
            agent_trace=agent_trace,
            greeting_turn=greeting_turn,
        )
    except Exception as exc:
        from services.brain.billing import release_turn_reservation
        from services.brain.outbound_safety import is_llm_provider_error

        release_turn_reservation(turn)
        if is_llm_provider_error(exc):
            from services.brain.llm_core_service import sanitize_llm_error
            from services.brain.silence import log_customer_generation_failure

            log_customer_generation_failure(stage="generate", extra={"blocker": sanitize_llm_error(exc)}, exc=exc)
            return TurnResult(
                stop_reason="failed_closed",
                envelope=FinalReplyEnvelope(decision="clarify"),
                extra={
                    "phase": "generate",
                    "llm_fail_soft": True,
                    "customer_silence": True,
                    "exception_class": type(exc).__name__,
                    "blocker": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "agent_trace": agent_trace,
                    **extra,
                },
            )
        raise
    finally:
        if result is not None and not _keep_generate_hold(result):
            from services.brain.billing import release_turn_reservation

            release_turn_reservation(turn)
    if result is not None:
        extra = {**extra, **dict(result.extra or {})}
    return await commit_pending_human_escalate(turn=turn, plan=plan, extra=extra, result=result, message=message)


async def run_agentic_dm_path(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    flow_base: dict[str, Any] | None = None,
    visual_reason: str = "",
) -> TurnResult:
    from services.brain.turn_pipeline import inbound_task_text

    task_text = inbound_task_text(turn, message)
    rewritten = await rewrite_queries(
        task_text, list(turn.history.messages), _response_language(turn), tenant_id=turn.tenant_id
    )
    if rewritten.get("rewritten") and rewritten["rewritten"].strip() != task_text.strip():
        task_text = rewritten["rewritten"]
        flow_base = _flow_extra(
            flow_base,
            ("context", "Resolved follow-up using recent conversation", {"variants": rewritten.get("variants")}),
        )
    plan_timer = StageTimer()
    plan = default_agentic_plan(task_text)
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
        destination=_destination(channel, turn),
        plan=plan,
        flow_extra=flow_base,
        visual_reason=visual_reason,
    )
