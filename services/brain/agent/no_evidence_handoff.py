"""Auto Live Chat handoff only when retrieval found no published answer."""

from __future__ import annotations

import re
from typing import Any

from services.ai_setup.capability_gates import human_handoff_enabled
from services.brain.actions.execute import execute_actions
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.enums import ReplyDecision, StopReason, TaskDisposition
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.stage_timeline import stamp
from services.brain.templates import owner_protocol_text

_INFO_TYPES = frozenset({"information", "hours", "comparison"})
_LIVE_KINDS = frozenset({"dm", "followup", "comment"})
_PRICED_FAMS = frozenset({"prices", "products", "services", "hours"})
_ACK_RE = re.compile(
    r"^\s*(?:"
    r"ok+|okay|k+|thanks|thank you|thx|ty|"
    r"hey+|hi+|hello|yo|"
    r"شكراً?|يسلمو|تمام|ماشي|اوك|أوك|حسناً?|"
    r"good|great|cool|nice|done|"
    r"wow+|waw+|wao+|whats|"
    r"love|loved|beautiful|amazing|perfect|cute|pretty|gorgeous|"
    r"mashallah|masha'? ?allah|"
    r"واو+|حلوة?|خطير|يجنن|روعه|روعة|تحفه|تحفة|حبيت|"
    r"👍|❤️|🙏|😊|🔥|😍|💕|✨"
    r")(?:\s+(?:thanks|thank you|شكراً?|يسلمو))*\s*[!.؟]*\s*$",
    re.IGNORECASE | re.UNICODE,
)
_QUESTION_RE = re.compile(
    r"("
    r"[?؟]"
    r"|\b(what|when|where|which|who|why|how|how much|tell me|do you|does this|"
    r"is there|are there|can you|could you|looking for)\b"
    r"|شو|وين|امتى|متى|كم|هل|ليش|كيف|عندكم|عندكن|بدي اعرف|خبرني|قلي"
    r"|سعر|دوام|غلى|كلفة|عنوان|العنون"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def is_comment_ack(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _ACK_RE.match(text):
        return True
    if len(text) <= 8 and not _QUESTION_RE.search(text) and not any(ch.isalnum() for ch in text):
        return True
    return False


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
        from services.brain.outbound_safety import looks_like_instruction_text
        from services.brain.silence import log_customer_generation_failure

        text = owner_protocol_text("handoff", lang)
        if text and looks_like_instruction_text(text):
            text = ""
        decision = "handoff_ack"
        dispositions = {task.id: "not_found" for task in plan.tasks if task.type in _INFO_TYPES}
        dispositions["handoff"] = "action_succeeded"
        messages = [OutboundMessage(destination=dest, text=text, protected=True)] if text else []
        if not text:
            extra["customer_silence"] = True
            log_customer_generation_failure(stage="handoff_owner_protocol_empty")
        stop_reason = "ok"
    else:
        from services.brain.silence import log_customer_generation_failure

        log_customer_generation_failure(stage="retrieve_not_found")
        decision = "clarify"
        dispositions = {task.id: "not_found" for task in plan.tasks if task.type in _INFO_TYPES}
        messages = []
        extra["customer_silence"] = True
        stop_reason = "failed_closed"

    agent_trace.append({"step": "FINAL", "decision": decision, "reason": "unanswered_not_found"})
    envelope = FinalReplyEnvelope(
        decision=decision,
        messages=messages,
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
