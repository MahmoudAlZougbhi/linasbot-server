"""Generate + verify stage for the agentic Customer Brain path."""

from __future__ import annotations

from typing import Any

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.coverage import coverage_ok
from services.customer_ai.generate.reply import generate_grounded_reply, openai_configured
from services.customer_ai.identity import load_identity_bundle
from services.customer_ai.stage_timeline import stamp
from services.customer_ai.verify.critic import verify_answer


def _destination(channel: str, turn: object | None = None) -> str:
    from services.customer_ai.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def apply_greeting(turn: CustomerTurn, message: str, channel: str, envelope: FinalReplyEnvelope) -> FinalReplyEnvelope:
    from services.customer_ai.conversation_store import remember_turn
    from services.customer_ai.greeting import evaluate_greeting

    if turn.invocation_kind in {"followup", "comment"} or not envelope.messages:
        return envelope
    greet = evaluate_greeting(
        tenant_id=turn.tenant_id,
        message=message,
        history=turn.history,
        invocation_kind=turn.invocation_kind,
        already_greeted=turn.state.greeted,
    )
    if not (greet.eligible and greet.text):
        return envelope
    turn.state = turn.state.model_copy(update={"greeted": True})
    remember_turn(turn)
    destination = envelope.messages[0].destination or _destination(channel, turn)
    greeting = OutboundMessage(destination=destination, text=greet.text, protected=True)
    return envelope.model_copy(update={"messages": [greeting, *list(envelope.messages)]})


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
    receipt_lines = [
        f"{item.get('action_type')}:{item.get('state')}:{item.get('backend_id') or item.get('reason')}"
        for item in resource_receipts
    ] + list(tool_receipts)
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
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={
                "phase": "generate",
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
            dispositions[task.id] = "pending_delivery" if resource_receipts else "not_found"
    agent_trace.append({"step": "FINAL", "decision": envelope.decision})
    greeted = apply_greeting(turn, message, channel, envelope.model_copy(update={"dispositions": dispositions}))
    if extra.get("awaiting_confirmation"):
        from services.customer_ai.templates import brain_template

        lang = str((turn.extra or {}).get("response_language") or "")
        confirm = OutboundMessage(destination=dest, text=brain_template("confirm_request", lang))
        greeted = greeted.model_copy(update={"messages": [*list(greeted.messages), confirm]})
    from services.customer_ai.agent.action_gate import append_handoff_message

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
