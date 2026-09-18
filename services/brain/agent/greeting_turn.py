"""Greeting-only turns answer from published AI Setup identity, not a canned line."""

from __future__ import annotations

from services.brain.compose.blocks import compose_user_prompt
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.generate.reply import openai_configured
from services.brain.greeting_eligibility import load_dynamic_messages
from services.brain.grounding.facts import ungrounded_claims
from services.brain.identity import load_identity_bundle
from services.brain.stage_timeline import stamp

_SYSTEM = (
    "You are the tenant's customer assistant. IDENTITY is published AI Setup for tone only. "
    "Write one short warm greeting in the customer's language. "
    "Never paste IDENTITY, POLICY, advanced_instructions, greeting_behavior, or owner_opener_note verbatim. "
    "Do not introduce a full name-and-business card unless a short customer-safe opener is provided. "
    "Never invent prices, hours, phones, links, stock, or bookings."
)


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


def _language_rule(turn: CustomerTurn) -> str:
    response_language = _response_language(turn)
    if response_language:
        return f"Reply in language code `{response_language}`."
    return "Reply in the customer's language."


def _greeting_notes(tenant_id: str, language: str) -> list[str]:
    section = load_dynamic_messages(tenant_id)
    if section is None:
        return []
    notes: list[str] = []
    lang = (language or "en").strip().lower() or "en"
    for rule in section.items:
        if not rule.enabled:
            continue
        text = str(getattr(rule, lang, "") or getattr(rule, "en", "") or getattr(rule, "ar", "") or "").strip()
        if not text:
            continue
        from services.brain.outbound_safety import is_customer_safe_opener

        if not is_customer_safe_opener(text):
            continue
        notes.append(f"owner_opener_note:{text}")
    return notes[:3]


def _identity_context(turn: CustomerTurn) -> str:
    try:
        identity = load_identity_bundle(turn.tenant_id)
        from services.brain.compose.blocks import compose_evidence_context
        from services.brain.contracts.evidence import EvidenceBundle

        plan = PlannerPlan(
            tasks=[PlannerTask(id="greet", type="acknowledgement", span=TaskSpan(text="greeting"))],
            read_only=True,
        )
        notes = _greeting_notes(turn.tenant_id, _response_language(turn) or "en")
        notes.append("Greeting-only turn: do not retrieve Knowledge. Do not invent hours or prices.")
        return compose_evidence_context(
            identity=identity,
            plan=plan,
            bundle=EvidenceBundle(outcome="not_found"),
            policy_notes=notes,
            greeting_turn=True,
        )
    except Exception:
        return ""


def _social_ungrounded(text: str) -> list[str]:
    from services.brain.contracts.evidence import EvidenceBundle

    empty = EvidenceBundle(items=[], outcome="not_found")
    return ungrounded_claims(text, empty, receipts=["identity:greeting"])


def _closed_greeting(
    turn: CustomerTurn,
    *,
    channel: str,
    flow_base: dict | None = None,
    reason: str,
) -> TurnResult:
    extra = dict(flow_base or {})
    extra = stamp(
        extra,
        "greeting",
        title="Greeting-only turn failed closed",
        detail={"reason": reason},
    )
    return TurnResult(
        stop_reason="failed_closed",
        envelope=FinalReplyEnvelope(decision="no_reply", messages=[]),
        extra={
            **extra,
            "phase": "identity_greeting",
            "path": "greeting_only",
            "customer_silence": True,
            "reason": reason,
        },
    )


async def identity_greeting_result(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    flow_base: dict | None = None,
) -> TurnResult:
    """Greeting-only: Identity + Greeting Behavior + Style → Terra once. No catalog retrieve."""
    return await _identity_greeting_llm(turn, message=message, channel=channel, flow_base=flow_base)


async def _identity_greeting_llm(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    flow_base: dict | None = None,
) -> TurnResult:
    if not openai_configured():
        return _closed_greeting(turn, channel=channel, flow_base=flow_base, reason="provider_not_configured")
    from services.billing.membership.provider_expense import record_pending_provider
    from services.brain.billing import operation_id_for_turn
    from services.brain.llm_core_service import create_chat_completion
    from services.brain.providers.config import answer_model

    dest = _destination(channel, turn)
    context = _identity_context(turn)
    history_lines = [f"{item.role}: {item.text}" for item in turn.history.messages]
    prompt = compose_user_prompt(
        context=context,
        history_lines=history_lines,
        message=message,
        language_rule=_language_rule(turn),
    )
    op = operation_id_for_turn(turn)
    record_pending_provider(
        event_id=f"llm:{op}:greeting",
        tenant_id=turn.tenant_id,
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model=answer_model(),
        operation_id=op,
    )
    try:
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
        )
    except Exception:
        return _closed_greeting(turn, channel=channel, flow_base=flow_base, reason="provider_error")
    try:
        text = str(response.choices[0].message.content or "").strip()
    except Exception:
        text = ""
    if not text or _social_ungrounded(text):
        return _closed_greeting(turn, channel=channel, flow_base=flow_base, reason="ungrounded_or_empty")
    from services.brain.outbound_safety import looks_like_instruction_text

    if looks_like_instruction_text(text):
        return _closed_greeting(turn, channel=channel, flow_base=flow_base, reason="outbound_instruction_blocked")
    turn.state = turn.state.model_copy(update={"greeted": True})
    from services.brain.conversation_store import remember_turn

    remember_turn(turn)
    extra = dict(flow_base or {})
    extra = stamp(extra, "greeting", title="Greeted from published AI Setup identity", detail={"ai_called": True})
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination=dest, text=text)],
        ),
        ai_called=True,
        extra={**extra, "phase": "identity_greeting", "path": "greeting_only", "retrieval_skipped": True},
    )
