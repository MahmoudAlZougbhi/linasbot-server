"""Greeting-only turns: same Terra session with IDENTITY. No second greeting LLM."""

from __future__ import annotations

from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.generate.reply import openai_configured
from services.brain.greeting_policy import load_dynamic_messages
from services.brain.identity import load_identity_bundle
from services.brain.stage_timeline import stamp


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


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


def _closed_greeting(
    turn: CustomerTurn,
    *,
    channel: str,
    flow_base: dict | None = None,
    reason: str,
) -> TurnResult:
    extra = dict(flow_base or {})
    extra = stamp(extra, "greeting", title="Greeting-only turn failed closed", detail={"reason": reason})
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
    """Greeting-only: Identity via the same Terra session. No catalog retrieve. No second LLM."""
    extra = dict(flow_base or {})
    extra["identity_ok"] = True
    extra["retrieval_skipped"] = True
    if not openai_configured():
        return _closed_greeting(turn, channel=channel, flow_base=extra, reason="provider_not_configured")
    from services.brain.agent.terra_turn import run_terra_turn

    plan = PlannerPlan(
        tasks=[PlannerTask(id="greet", type="acknowledgement", span=TaskSpan(text="greeting"))],
        read_only=True,
    )
    bundle = EvidenceBundle(outcome="not_found")
    result = await run_terra_turn(
        turn,
        message=message,
        channel=channel,
        dest=_destination(channel, turn),
        plan=plan,
        bundle=bundle,
        structured_facts={},
        visual_reason="",
        extra=extra,
        evidence=[],
        agent_trace=[],
        greeting_turn=True,
    )
    if result.extra is None:
        result.extra = {}
    result.extra["retrieval_skipped"] = True
    result.extra.setdefault("path", "greeting_only")
    result.extra.setdefault("phase", "identity_greeting")
    return result
