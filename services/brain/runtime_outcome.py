"""Turn outcome helpers shared by Customer Brain DM and comment entrypoints."""

from __future__ import annotations

from typing import Any

from services.brain.billing import apply_message_billing
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.gates import GateDecision
from services.brain.reply.models import CustomerReplyOutcome
from services.brain.turn_pipeline import run_dm_after_gates


def scrub_instruction_reply(result: TurnResult, reply: str | None) -> tuple[str | None, dict[str, Any]]:
    extra = dict(result.extra or {})
    text = (reply or "").strip()
    if not text:
        return reply, extra
    from services.brain.outbound_safety import looks_like_instruction_text

    if not looks_like_instruction_text(text):
        return reply, extra
    tenant_id = str(extra.get("tenant_id") or "")
    lang = str(extra.get("response_language") or "")
    inbound = str(extra.get("inbound_preview") or "")
    path = str(extra.get("path") or extra.get("phase") or "")
    extra["outbound_instruction_blocked"] = True
    extra["blocker"] = str(extra.get("blocker") or "outbound_instruction_blocked")[:200]
    extra["exception_class"] = str(extra.get("exception_class") or "OutboundInstructionBlocked")
    extra["outbound_replacement"] = "silence"
    extra["customer_silence"] = True
    _ = (tenant_id, lang, inbound, path)
    from services.brain.silence import log_customer_generation_failure

    log_customer_generation_failure(stage="outbound_instruction_blocked", extra=extra)
    return None, extra


def outcome_from_result(result: TurnResult, *, comment_surface: bool = False) -> CustomerReplyOutcome:
    extra = dict(result.extra or {})
    safe_messages = []
    for item in result.envelope.messages:
        text, extra = scrub_instruction_reply(result, item.text)
        if text:
            safe_messages.append(item.model_copy(update={"text": text}))
    public_raw = result.envelope.public_comment_text
    private_raw = result.envelope.private_dm_text
    public, extra = scrub_instruction_reply(result, public_raw or None)
    private, extra = scrub_instruction_reply(result, private_raw or None)
    if comment_surface:
        reply = public or None
        has_out = bool(public or private)
    else:
        reply = (safe_messages[0].text if safe_messages else None) or (result.envelope.reply_text or None)
        reply, extra = scrub_instruction_reply(result, reply)
        has_out = bool(reply)
    stop = result.stop_reason != "ok" or not has_out
    return CustomerReplyOutcome(
        stop=stop,
        reply=reply,
        reason=result.stop_reason if result.stop_reason != "ok" else "",
        evidence_status="policy_stop" if stop else "ok",
        metadata={
            "ai_called": result.ai_called,
            "cost_status": "none" if not result.ai_called else "tracked",
            "customer_engine": "brain",
            "outbound_messages": [item.model_dump() for item in safe_messages],
            "public_comment_text": public or "",
            "private_dm_text": private or "",
            **extra,
            "operation_id": extra.get("operation_id") or "",
        },
    )


def destination_for(turn: CustomerTurn, channel: str) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel or turn.channel)


def gate_result(turn: CustomerTurn, gate: GateDecision, channel: str) -> TurnResult:
    extra = {"gate": gate.detail}
    if gate.reason == "restricted" and gate.reply_text:
        extra["restricted_topic_id"] = gate.detail
        return TurnResult(
            stop_reason="restricted",
            envelope=FinalReplyEnvelope(
                decision="deterministic",
                messages=[
                    OutboundMessage(destination=destination_for(turn, channel), text=gate.reply_text, protected=True)
                ],
            ),
            extra=extra,
        )
    return TurnResult(stop_reason=gate.reason, extra=extra)


async def run_billed(turn: CustomerTurn, *, message: str, channel: str) -> TurnResult:
    from services.brain.billing import release_turn_reservation

    try:
        return apply_message_billing(turn, await run_dm_after_gates(turn, message=message, channel=channel))
    except Exception:
        release_turn_reservation(turn)
        raise


def language_extra(*, detected_language: str = "", response_language: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    detected = (detected_language or "").strip()
    response = (response_language or "").strip()
    if detected:
        out["detected_language"] = detected
    if response:
        out["response_language"] = response
    return out
