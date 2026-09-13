"""Auto Live Chat handoff only when retrieval found no published answer."""

from __future__ import annotations

import re
from typing import Any

from services.cm.capability_gates import human_handoff_enabled
from services.customer_ai.actions.execute import execute_actions
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.enums import ReplyDecision, StopReason, TaskDisposition
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.stage_timeline import stamp
from services.customer_ai.templates import brain_template

_INFO_TYPES = frozenset({"information", "hours", "comparison"})
_LIVE_KINDS = frozenset({"dm", "followup"})
_PRICED_FAMS = frozenset({"prices", "products", "services", "hours"})
_ACK_RE = re.compile(
    r"^\s*(?:"
    r"ok+|okay|k+|thanks|thank you|thx|ty|"
    r"شكراً?|يسلمو|تمام|ماشي|اوك|أوك|حسناً?|"
    r"good|great|cool|nice|done|"
    r"👍|❤️|🙏|😊"
    r")(?:\s+(?:thanks|thank you|شكراً?|يسلمو))*\s*[!.؟]*\s*$",
    re.IGNORECASE | re.UNICODE,
)
_QUESTION_RE = re.compile(
    r"("
    r"[?؟]"
    r"|\b(what|when|where|which|who|why|how|how much|tell me|do you|does this|"
    r"is there|are there|can you|could you|looking for)\b"
    r"|شو|وين|امتى|متى|كم|هل|ليش|كيف|عندكم|عندكن|بدي اعرف|خبرني|قلي"
    r"|سعر|دوام|غلى|كلفة"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def should_handoff_unanswered(
    *,
    plan: PlannerPlan,
    outcome: str,
    invocation_kind: str = "dm",
    message: str = "",
) -> bool:
    """True only for a real unanswered question, never small-talk or operational misses."""
    if str(invocation_kind or "dm") not in _LIVE_KINDS:
        return False
    if outcome != "not_found":
        return False
    types = {task.type for task in plan.tasks}
    if not types.intersection(_INFO_TYPES):
        return False
    if _ACK_RE.match((message or "").strip()):
        return False
    if types.intersection({"hours", "comparison"}):
        return True
    if _priced_or_named_info(plan):
        return True
    return "information" in types and bool(_QUESTION_RE.search(message or ""))


def _priced_or_named_info(plan: PlannerPlan) -> bool:
    for task in plan.tasks:
        if task.type != "information":
            continue
        families = set(task.source_families or [])
        if families.intersection(_PRICED_FAMS):
            return True
        if task.entity_mentions:
            return True
    return False


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def _handoff_allowed(tenant_id: str) -> bool:
    try:
        return bool(human_handoff_enabled(tenant_id))
    except Exception:
        return False


async def unanswered_question_result(
    turn: CustomerTurn,
    *,
    message: str,
    plan: PlannerPlan,
    dest: str,
    lang: str,
    extra: dict[str, Any],
    agent_trace: list[dict[str, Any]],
    outcome: str,
    evidence: list[dict[str, str]],
    structured_facts: dict[str, Any],
    resource_receipts: list[dict],
    visual_reason: str,
    tool_rows: list[dict[str, Any]],
) -> TurnResult | None:
    if not should_handoff_unanswered(
        plan=plan,
        outcome=outcome,
        invocation_kind=turn.invocation_kind,
        message=message,
    ):
        return None

    already_ok = bool(extra.get("handoff_ok"))
    dumped: list[dict[str, Any]] = list(extra.get("handoff_receipts") or [])
    ok = already_ok
    if not already_ok and _handoff_allowed(turn.tenant_id):
        receipts = await execute_actions(
            turn=turn,
            proposals=ActionProposalSet(
                actions=[ActionProposal(task_id="unanswered", action_type="escalate_to_human")]
            ),
            customer_text=message,
        )
        dumped = [item.model_dump() for item in receipts.receipts]
        ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)

    extra = dict(extra)
    extra["handoff_ok"] = ok
    extra["handoff_receipts"] = dumped
    extra["receipts"] = list(extra.get("receipts") or []) + dumped
    extra["no_evidence_handoff"] = True

    decision: ReplyDecision
    stop_reason: StopReason = "ok"
    dispositions: dict[str, TaskDisposition]
    if ok:
        text = brain_template("no_evidence_handoff", lang)
        decision = "handoff_ack"
        dispositions = {task.id: "not_found" for task in plan.tasks if task.type in _INFO_TYPES}
        dispositions["handoff"] = "action_succeeded"
    else:
        text = brain_template("no_evidence", lang)
        decision = "clarify"
        dispositions = {task.id: "not_found" for task in plan.tasks if task.type in _INFO_TYPES}

    agent_trace.append({"step": "FINAL", "decision": decision, "reason": "unanswered_not_found"})
    envelope = FinalReplyEnvelope(
        decision=decision,
        messages=[OutboundMessage(destination=dest, text=text, protected=True)],
        dispositions=dispositions,
    )
    return TurnResult(
        stop_reason=stop_reason,
        envelope=envelope,
        extra=_flow_extra(
            {
                "phase": "no_evidence_handoff" if ok else "no_evidence",
                "retrieval_outcome": outcome,
                "plan": plan.model_dump(),
                "visual": visual_reason,
                "receipts": list(resource_receipts) + dumped,
                "evidence_preview": evidence,
                "agent_trace": agent_trace,
                "structured_facts": structured_facts,
                "tool_calls": tool_rows,
                **extra,
            },
            (
                "handoff" if ok else "search_empty",
                "Handed off unanswered question to a human teammate"
                if ok
                else "No published evidence found for this question",
                {"decision": decision, "retrieval_outcome": outcome},
            ),
        ),
    )
