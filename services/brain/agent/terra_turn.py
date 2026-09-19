"""One Terra agent session per customer inbound: tools + reply + one grounding repair."""

from __future__ import annotations

from typing import Any

from services.brain.agent.terra_prompt import build_terra_messages
from services.brain.agent.terra_request_round import hydrate_request_snapshot
from services.brain.agent.terra_session import repair_rewrite, run_terra_tool_loop
from services.brain.agent.tool_calls import skip_tools_for_turn
from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.compose.blocks import grounding_feedback
from services.brain.contracts.enums import TaskDisposition
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.generate.reply import openai_configured
from services.brain.identity import load_identity_bundle
from services.brain.verify.critic import verify_answer

_ANSWERED = {"information", "hours", "comparison"}


def _used_ids(bundle: EvidenceBundle) -> list[str]:
    seen: list[str] = []
    for item in bundle.items:
        if item.evidence_id and item.evidence_id not in seen:
            seen.append(item.evidence_id)
    return seen


def _build_receipts(
    turn: CustomerTurn, extra: dict[str, Any], resource_receipts: list[dict], tool_receipts: list[str]
) -> list[str]:
    from services.brain.actions.human_handoff_policy import policy_receipts
    from services.brain.tools.resource_inventory import format_inventory_receipt, remember_previous_inventory

    lines = [
        f"{item.get('action_type')}:{item.get('state')}:{item.get('backend_id') or item.get('reason')}"
        for item in resource_receipts
    ]
    lines.extend(tool_receipts)
    lines.extend(policy_receipts(extra))
    previous = remember_previous_inventory(turn)
    if previous:
        lines.append(format_inventory_receipt(previous, prefix="previous_inventory"))
    if extra.get("identity_ok"):
        lines.append("identity:greeting")
    return lines


def _envelope(
    text: str, dest: str, plan: PlannerPlan, bundle: EvidenceBundle, extra: dict[str, Any]
) -> FinalReplyEnvelope:
    dispositions: dict[str, TaskDisposition] = {task.id: "answered" for task in plan.tasks if task.type in _ANSWERED}
    for task in plan.tasks:
        if task.type == "acknowledgement":
            dispositions[task.id] = "answered"
        if task.type == "human_request":
            dispositions[task.id] = "awaiting_customer"
        if extra.get("comment_invite_dm") and task.type in {"product_request", "service_request"}:
            dispositions[task.id] = "policy_suppressed"
    return FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination=dest, text=text)],
        used_evidence_ids=_used_ids(bundle),
        dispositions=dispositions,
    )


def _closed(*, extra: dict[str, Any], agent_trace: list[dict[str, Any]], reason: str) -> TurnResult:
    from services.brain.silence import log_customer_generation_failure

    log_customer_generation_failure(stage=reason)
    agent_trace.append({"step": "FINAL", "decision": "clarify", "reason": reason})
    return TurnResult(
        stop_reason="failed_closed",
        envelope=FinalReplyEnvelope(decision="clarify"),
        extra={
            "phase": "generate",
            "llm_fail_soft": True,
            "customer_silence": True,
            "agent_trace": agent_trace,
            **extra,
        },
    )


async def run_terra_turn(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    dest: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    structured_facts: dict[str, Any],
    visual_reason: str,
    extra: dict[str, Any],
    evidence: list[dict[str, str]],
    agent_trace: list[dict[str, Any]],
    greeting_turn: bool = False,
) -> TurnResult:
    extra = {**dict(extra), **hydrate_request_snapshot(turn)}
    turn.extra = {**dict(turn.extra or {}), **extra}
    if not openai_configured():
        agent_trace.append({"step": "FINAL", "decision": "no_reply", "reason": "provider_not_configured"})
        return TurnResult(
            stop_reason="provider_not_configured",
            envelope=FinalReplyEnvelope(decision="no_reply", used_evidence_ids=_used_ids(bundle)),
            extra={
                "phase": "awaiting_generate",
                "retrieval_outcome": bundle.outcome,
                "plan": plan.model_dump(),
                **extra,
            },
        )
    identity = load_identity_bundle(turn.tenant_id)
    skip = skip_tools_for_turn(turn, extra)
    snapshot = extra.get("request_state") if isinstance(extra.get("request_state"), dict) else {}
    greet = bool(greeting_turn or extra.get("identity_ok"))
    messages = build_terra_messages(
        turn=turn,
        message=message,
        plan=plan,
        bundle=bundle,
        identity=identity,
        receipts=_build_receipts(turn, extra, [], []),
        greeting_turn=greet,
    )
    text, extra, tool_receipts, _rows, llm_calls = await run_terra_tool_loop(
        turn,
        messages=messages,
        message=message,
        extra=extra,
        skip=skip,
        snapshot=snapshot,
        trace=agent_trace,
        budget=DEFAULT_BUDGETS.max_tool_calls,
    )
    from services.brain.facts.receipt_align import align_fact_receipts
    from services.brain.stage_timeline import evidence_preview
    from services.brain.tools.resource_delivery import apply_resource_tool_side_effects

    tool_receipts = align_fact_receipts(tool_receipts, bundle)
    bundle, extra, evidence, resource_receipts = apply_resource_tool_side_effects(
        turn, bundle, extra, evidence_preview=evidence_preview
    )
    receipt_lines = _build_receipts(turn, extra, resource_receipts, tool_receipts)
    extra["terra_llm_calls"] = llm_calls
    if not text:
        if turn.invocation_kind == "followup":
            return TurnResult(
                stop_reason="ok",
                envelope=FinalReplyEnvelope(decision="no_reply"),
                extra={"phase": "followup_no_reply", "plan": plan.model_dump(), "agent_trace": agent_trace, **extra},
            )
        return _closed(extra=extra, agent_trace=agent_trace, reason="empty_generate")
    from services.brain.outbound_safety import looks_like_instruction_text

    if greet and looks_like_instruction_text(text):
        return _closed(
            extra={**extra, "phase": "identity_greeting"},
            agent_trace=agent_trace,
            reason="outbound_instruction_blocked",
        )
    repairs = max(0, DEFAULT_BUDGETS.repair_attempts)
    verdict = await verify_answer(
        reply_text=text,
        plan=plan,
        bundle=bundle,
        structured_facts=structured_facts,
        receipts=receipt_lines,
        message=message,
    )
    agent_trace.append({"step": "VERIFY", "verdict": verdict.verdict, "attempt": 0})
    if verdict.verdict != "PASS" and repairs and verdict.repair_instruction:
        feedback = grounding_feedback(list(verdict.unsupported_claims) or [verdict.repair_instruction])
        text, llm_calls = await repair_rewrite(turn, messages, feedback=feedback, llm_calls=llm_calls)
        extra["terra_llm_calls"] = llm_calls
        if not text or (greet and looks_like_instruction_text(text)):
            return _closed(extra=extra, agent_trace=agent_trace, reason="verify_repair")
        verdict = await verify_answer(
            reply_text=text,
            plan=plan,
            bundle=bundle,
            structured_facts=structured_facts,
            receipts=receipt_lines,
            message=message,
        )
        agent_trace.append({"step": "VERIFY", "verdict": verdict.verdict, "attempt": 1})
    if verdict.verdict != "PASS":
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify", used_evidence_ids=_used_ids(bundle)),
            extra={
                "phase": "verify",
                "plan": plan.model_dump(),
                "agent_trace": agent_trace,
                "verify": {"verdict": verdict.verdict, "unsupported_claims": verdict.unsupported_claims},
                **extra,
            },
        )
    from services.brain.agent.generate_path import wrap_verified_reply

    return wrap_verified_reply(
        turn,
        message=message,
        channel=channel,
        dest=dest,
        plan=plan,
        bundle=bundle,
        structured_facts=structured_facts,
        visual_reason=visual_reason,
        resource_receipts=resource_receipts,
        extra=extra,
        evidence=evidence,
        agent_trace=agent_trace,
        envelope=_envelope(text, dest, plan, bundle, extra),
        reply_text=text,
    )
