"""Grounded final reply. Missing OpenAI is provider_not_configured, not a fake answer.

Generation is grounding-gated: a reply that fails the deterministic checks gets one repair
attempt with explicit feedback (budgets.repair_attempts), then the turn fails closed with an
empty clarify envelope. No evidence means no factual reply at all.
"""

from __future__ import annotations

import os

from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.compose.blocks import (
    compose_evidence_context,
    compose_user_prompt,
    grounding_feedback,
    system_prompt,
)
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.brain.contracts.turn import CustomerTurn
from services.brain.grounding.claims import claims_fail_closed, verify_claims
from services.brain.grounding.contradiction import detect_amount_contradictions
from services.brain.grounding.facts import ungrounded_amounts, ungrounded_claims
from services.brain.identity import IdentityBundle
from services.brain.providers.config import answer_model

__all__ = ["generate_grounded_reply", "openai_configured", "ungrounded_amounts"]

_ANSWERED_TASK_TYPES = {"information", "hours", "comparison"}


def openai_configured() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def _clarify() -> FinalReplyEnvelope:
    return FinalReplyEnvelope(decision="clarify", messages=[])


def _used_evidence_ids(bundle: EvidenceBundle) -> list[str]:
    seen: list[str] = []
    for item in bundle.items:
        if item.evidence_id and item.evidence_id not in seen:
            seen.append(item.evidence_id)
    return seen


def _language_rule(turn: CustomerTurn) -> str:
    response_language = str((turn.extra or {}).get("response_language") or "").strip()
    if response_language:
        return f"Reply in language code `{response_language}`."
    return "Reply in the customer's language."


async def _ask_model(*, turn: CustomerTurn, prompt: str, attempt: int) -> str:
    from services.billing.membership.provider_expense import record_pending_provider
    from services.brain.billing import operation_id_for_turn
    from services.brain.llm_core_service import create_chat_completion

    op = operation_id_for_turn(turn)
    record_pending_provider(
        event_id=f"llm:{op}" if attempt == 0 else f"llm:{op}:repair{attempt}",
        tenant_id=turn.tenant_id,
        category="llm_generation",
        feature="followup" if turn.invocation_kind == "followup" else "customer_chat",
        provider="openai",
        model=answer_model(),
        operation_id=op,
    )
    try:
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
        )
    except Exception as exc:
        from services.brain.llm_core_service import sanitize_llm_error

        print(f"[generate_grounded_reply] fail-soft {type(exc).__name__}: {sanitize_llm_error(exc)}")
        return ""
    try:
        return str(response.choices[0].message.content or "").strip()
    except Exception:
        return ""


async def generate_grounded_reply(
    *,
    turn: CustomerTurn,
    message: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    identity: IdentityBundle | None,
    destination: str,
    receipts: list[str] | None = None,
) -> FinalReplyEnvelope | None:
    if not openai_configured():
        return None
    if not bundle.items:
        # No provenance means nothing factual can be said. Ask instead of guessing.
        return _clarify()
    conflicts = detect_amount_contradictions("", items=list(bundle.items))
    if conflicts:
        return FinalReplyEnvelope(
            decision="clarify",
            messages=[],
            used_evidence_ids=_used_evidence_ids(bundle),
            dispositions={task.id: "blocked" for task in plan.tasks if task.type in _ANSWERED_TASK_TYPES},
        )
    policy_notes: list[str] = []
    if turn.tenant_id.strip():
        from services.brain.planner.published_rules import request_rule_notes

        policy_notes = request_rule_notes(turn.tenant_id)
    comment_rule = str((turn.extra or {}).get("comment_rule_text") or "").strip()
    if comment_rule:
        policy_notes.append(f"comment_rule:{comment_rule[:1200]}")
    comment_mode = str((turn.extra or {}).get("comment_mode") or "").strip()
    if comment_mode.startswith("ai"):
        policy_notes.append(
            f"AI comment mode={comment_mode}. Write customer-facing wording from Comment Rules and Style. "
            "Do not use canned system copy such as 'Sent you a DM.'"
        )
    from services.brain.greeting import evaluate_greeting, is_greeting_only

    if turn.invocation_kind not in {"followup", "comment"} and not is_greeting_only(message):
        greet = evaluate_greeting(
            tenant_id=turn.tenant_id,
            message=message,
            history=turn.history,
            invocation_kind=turn.invocation_kind,
            already_greeted=turn.state.greeted,
        )
        if greet.eligible and greet.text:
            from services.brain.outbound_safety import is_customer_safe_opener

            if is_customer_safe_opener(greet.text):
                policy_notes.append(f"owner_opener_note:{greet.text}")
                policy_notes.append(
                    "If this starts a session, weave at most one short greeting into the same reply. "
                    "Do not prepend a second greeting."
                )
    if (turn.extra or {}).get("awaiting_confirmation"):
        policy_notes.append("A request is awaiting customer confirmation. Ask to confirm; do not claim it was submitted.")
    context = compose_evidence_context(
        identity=identity,
        plan=plan,
        bundle=bundle,
        policy_notes=policy_notes or None,
        receipts=receipts,
        followup_goal=turn.followup_goal,
    )
    history_lines = [f"{item.role}: {item.text}" for item in turn.history.messages]
    attempts = max(1, DEFAULT_BUDGETS.repair_attempts + 1)
    feedback = ""
    for attempt in range(attempts):
        prompt = compose_user_prompt(
            context=context,
            history_lines=history_lines,
            message=message,
            language_rule=_language_rule(turn),
            grounding_feedback_text=feedback,
        )
        text = await _ask_model(turn=turn, prompt=prompt, attempt=attempt)
        reasons = ungrounded_claims(text, bundle, receipts, message=message, plan=plan)
        verdicts = verify_claims(text, bundle, receipts=receipts)
        if not reasons and not claims_fail_closed(verdicts):
            return FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination=destination, text=text)],
                used_evidence_ids=_used_evidence_ids(bundle),
                dispositions={task.id: "answered" for task in plan.tasks if task.type in _ANSWERED_TASK_TYPES},
            )
        feedback = grounding_feedback(reasons or [v.reason or v.status for v in verdicts if v.status != "SUPPORTED"])
    return _clarify()
