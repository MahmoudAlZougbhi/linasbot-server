"""Compose the single Terra user context: identity, evidence, request_state, comments."""

from __future__ import annotations

from services.brain.agent.terra_tools import TOOL_USE_RULES
from services.brain.compose.blocks import compose_evidence_context, compose_user_prompt, system_prompt
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.turn import CustomerTurn
from services.brain.identity import IdentityBundle


def language_rule(turn: CustomerTurn) -> str:
    response_language = str((turn.extra or {}).get("response_language") or "").strip()
    if response_language:
        return f"Reply in language code `{response_language}`."
    return "Reply in the customer's language."


def collect_policy_notes(turn: CustomerTurn, plan: PlannerPlan, *, message: str) -> list[str]:
    extra = turn.extra or {}
    policy_notes: list[str] = []
    if turn.tenant_id.strip():
        fallback: list[str] | None = None
        state = extra.get("request_state")
        if not (isinstance(state, dict) and state.get("module_enabled")):
            from services.brain.planner.published_rules import request_rule_notes

            fallback = request_rule_notes(turn.tenant_id)
        from services.brain.agent.request_policy import policy_notes_for_turn

        policy_notes = policy_notes_for_turn(turn, fallback_tenant_notes=fallback)
    comment_rule = str(extra.get("comment_rule_text") or "").strip()
    from services.brain.actions.human_handoff_policy import human_policy_notes
    from services.brain.comments.public_request_policy import comment_request_policy_notes
    from services.brain.comments.surface_prompt import (
        comment_surface_policy_notes,
        extra_policy_notes,
        merge_policy_notes,
    )

    policy_notes = merge_policy_notes(
        policy_notes,
        [f"comment_rule:{comment_rule[:1200]}"] if comment_rule else [],
        comment_surface_policy_notes(turn),
        human_policy_notes(turn, plan, extra),
        comment_request_policy_notes(turn, plan),
        extra_policy_notes(turn),
    )
    from services.brain.greeting_policy import evaluate_greeting

    if turn.invocation_kind not in {"followup", "comment"}:
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
    return policy_notes


def build_terra_messages(
    *,
    turn: CustomerTurn,
    message: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    identity: IdentityBundle | None,
    receipts: list[str] | None,
    greeting_turn: bool = False,
) -> list[dict[str, str]]:
    extra = turn.extra or {}
    policy_notes = collect_policy_notes(turn, plan, message=message)
    if greeting_turn:
        policy_notes.append("Greeting-only turn: do not invent hours, prices, phones, or bookings.")
    nag = extra.get("request_state") if isinstance(extra.get("request_state"), dict) else {}
    if nag.get("nag_policy"):
        policy_notes.append(str(nag.get("nag_policy")))
    context = compose_evidence_context(
        identity=identity,
        plan=plan,
        bundle=bundle,
        policy_notes=policy_notes or None,
        receipts=receipts,
        followup_goal=turn.followup_goal,
        greeting_turn=greeting_turn,
        surface=str(getattr(turn, "surface", "") or ""),
        invocation_kind=str(getattr(turn, "invocation_kind", "") or ""),
    )
    from services.brain.comments.surface_prompt import history_lines_for_prompt

    prompt = compose_user_prompt(
        context=context,
        history_lines=history_lines_for_prompt(turn),
        message=message,
        language_rule=language_rule(turn),
    )
    system = system_prompt(
        surface=str(getattr(turn, "surface", "") or ""),
        invocation_kind=str(getattr(turn, "invocation_kind", "") or ""),
    )
    return [
        {"role": "system", "content": f"{system}\n{TOOL_USE_RULES}"},
        {"role": "user", "content": prompt},
    ]
