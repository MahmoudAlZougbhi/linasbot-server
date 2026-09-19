"""Generate + verify stage for the agentic Customer Brain path."""

from __future__ import annotations

from typing import Any

from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.coverage import coverage_ok
from services.brain.generate.reply import generate_grounded_reply, openai_configured
from services.brain.identity import load_identity_bundle
from services.brain.stage_timeline import stamp
from services.brain.verify.critic import verify_answer


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def apply_greeting(turn: CustomerTurn, message: str, channel: str, envelope: FinalReplyEnvelope) -> FinalReplyEnvelope:
    """Terra owns conversational copy. Do not concatenate a second greeting after generation."""
    _ = (turn, message, channel)
    return envelope


async def generate_verified(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    dest: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    structured_facts: dict[str, Any],
    visual_reason: str,
    resource_receipts: list[dict],
    tool_receipts: list[str],
    agent_trace: list[dict[str, Any]],
    extra: dict[str, Any],
    evidence: list[dict[str, str]],
) -> TurnResult:
    if not openai_configured():
        agent_trace.append({"step": "FINAL", "decision": "no_reply", "reason": "provider_not_configured"})
        return TurnResult(
            stop_reason="provider_not_configured",
            envelope=FinalReplyEnvelope(
                decision="no_reply",
                used_evidence_ids=[item.evidence_id for item in bundle.items],
            ),
            extra={
                "phase": "awaiting_generate",
                "retrieval_outcome": bundle.outcome,
                "plan": plan.model_dump(),
                "receipts": list(resource_receipts),
                "agent_trace": agent_trace,
                "structured_facts": structured_facts,
                **extra,
            },
        )
    identity = load_identity_bundle(turn.tenant_id)
    from services.brain.actions.human_handoff_policy import policy_receipts

    receipt_lines = [
        f"{item.get('action_type')}:{item.get('state')}:{item.get('backend_id') or item.get('reason')}"
        for item in resource_receipts
    ]
    receipt_lines.extend(tool_receipts)
    receipt_lines.extend(policy_receipts(extra))
    from services.brain.tools.resource_inventory import format_inventory_receipt, remember_previous_inventory

    previous = remember_previous_inventory(turn)
    if previous:
        receipt_lines.append(format_inventory_receipt(previous, prefix="previous_inventory"))
    envelope = await generate_grounded_reply(
        turn=turn,
        message=message,
        plan=plan,
        bundle=bundle,
        identity=identity,
        destination=dest,
        receipts=receipt_lines,
    )
    if envelope is None or not envelope.messages:
        agent_trace.append({"step": "FINAL", "decision": "clarify", "reason": "empty_generate"})
        if turn.invocation_kind == "followup":
            return TurnResult(
                stop_reason="ok",
                envelope=FinalReplyEnvelope(decision="no_reply"),
                extra={
                    "phase": "followup_no_reply",
                    "plan": plan.model_dump(),
                    "receipts": list(resource_receipts),
                    "agent_trace": agent_trace,
                    **extra,
                },
            )
        from services.brain.silence import log_customer_generation_failure

        log_customer_generation_failure(stage="empty_generate")
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={
                "phase": "generate",
                "llm_fail_soft": True,
                "customer_silence": True,
                "plan": plan.model_dump(),
                "receipts": list(resource_receipts),
                "agent_trace": agent_trace,
                **extra,
            },
        )

    reply_text = "\n".join(item.text for item in envelope.messages if (item.text or "").strip())
    repairs = max(0, DEFAULT_BUDGETS.verifier_repairs)
    for attempt in range(repairs + 1):
        verdict = await verify_answer(
            reply_text=reply_text,
            plan=plan,
            bundle=bundle,
            structured_facts=structured_facts,
            receipts=receipt_lines,
            message=message,
        )
        agent_trace.append(
            {
                "step": "VERIFY",
                "verdict": verdict.verdict,
                "unsupported_claims": list(verdict.unsupported_claims),
                "missing_tasks": list(verdict.missing_tasks),
                "attempt": attempt,
            }
        )
        if verdict.verdict == "PASS":
            break
        if attempt >= repairs or not verdict.repair_instruction:
            return TurnResult(
                stop_reason="failed_closed",
                envelope=FinalReplyEnvelope(decision="clarify", used_evidence_ids=envelope.used_evidence_ids),
                extra={
                    "phase": "verify",
                    "plan": plan.model_dump(),
                    "agent_trace": agent_trace,
                    "verify": {
                        "verdict": verdict.verdict,
                        "unsupported_claims": verdict.unsupported_claims,
                        "missing_tasks": verdict.missing_tasks,
                    },
                    "structured_facts": structured_facts,
                    **extra,
                },
            )
        envelope = await generate_grounded_reply(
            turn=turn,
            message=f"{message}\n\nRepair: {verdict.repair_instruction}",
            plan=plan,
            bundle=bundle,
            identity=identity,
            destination=dest,
            receipts=receipt_lines,
        )
        if envelope is None or not envelope.messages:
            return TurnResult(
                stop_reason="failed_closed",
                envelope=FinalReplyEnvelope(decision="clarify"),
                extra={"phase": "verify_repair", "agent_trace": agent_trace, **extra},
            )
        reply_text = "\n".join(item.text for item in envelope.messages if (item.text or "").strip())

    if not coverage_ok(message, plan, envelope.dispositions, reply_text=reply_text, decision=envelope.decision):
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify", used_evidence_ids=envelope.used_evidence_ids),
            extra={
                "phase": "coverage",
                "plan": plan.model_dump(),
                "receipts": list(resource_receipts),
                "agent_trace": agent_trace,
                **extra,
            },
        )
    faq_items = [item for item in bundle.items if item.source_family == "faq"]
    dispositions = dict(envelope.dispositions)
    for task in plan.tasks:
        if task.type == "resource_request" and task.id not in dispositions:
            if resource_receipts:
                dispositions[task.id] = "pending_delivery"
            elif extra.get("resource_inventory") is not None:
                dispositions[task.id] = "awaiting_customer"
            else:
                dispositions[task.id] = "not_found"
    agent_trace.append({"step": "FINAL", "decision": envelope.decision})
    greeted = apply_greeting(turn, message, channel, envelope.model_copy(update={"dispositions": dispositions}))
    from services.brain.agent.action_gate import append_handoff_message

    lang = str((turn.extra or {}).get("response_language") or "")
    greeted = append_handoff_message(greeted, extra, dest=dest, lang=lang)
    out_extra = _flow_extra(
        {
            "phase": "generate",
            "plan": plan.model_dump(),
            "visual": visual_reason,
            "faq_used": bool(faq_items),
            "faq_id": faq_items[0].source_id if faq_items else "",
            "used_evidence_ids": list(envelope.used_evidence_ids),
            "receipts": list(extra.get("receipts") or []) + list(resource_receipts),
            "agent_trace": agent_trace,
            "structured_facts": structured_facts,
            "evidence_preview": evidence,
            **{key: value for key, value in extra.items() if key != "receipts"},
        },
        (
            "generate",
            "Composed grounded AI reply from evidence",
            {"decision": envelope.decision, "used_evidence_ids": list(envelope.used_evidence_ids)},
        ),
    )
    return TurnResult(
        stop_reason="ok",
        envelope=greeted,
        ai_called=True,
        extra=out_extra,
    )
