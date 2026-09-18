"""Exact / semantic FAQ turn envelopes for the DM pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.faq_exact import find_published_exact_faq
from services.brain.faq_freshness import faq_static_allowed


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


def faq_envelope(
    turn: CustomerTurn,
    message: str,
    channel: str,
    *,
    text: str,
    extra: dict[str, Any],
    apply_greeting: Callable[[CustomerTurn, str, str, FinalReplyEnvelope], FinalReplyEnvelope],
) -> TurnResult:
    destination = _destination(channel, turn)
    envelope = apply_greeting(
        turn,
        message,
        channel,
        FinalReplyEnvelope(
            decision="deterministic",
            messages=[OutboundMessage(destination=destination, text=text, protected=True)],
            used_evidence_ids=list(extra.get("used_evidence_ids") or []),
            dispositions={"faq": "answered"},
        ),
    )
    return TurnResult(stop_reason="ok", envelope=envelope, extra=extra)


def exact_faq_result(
    turn: CustomerTurn,
    message: str,
    channel: str,
    *,
    apply_greeting: Callable[[CustomerTurn, str, str, FinalReplyEnvelope], FinalReplyEnvelope],
) -> TurnResult | None:
    if turn.invocation_kind == "followup" or not message.strip():
        return None
    faq = find_published_exact_faq(turn.tenant_id, message)
    if not faq or not faq_static_allowed(faq.answer, tenant_id=turn.tenant_id):
        return None
    return faq_envelope(
        turn,
        message,
        channel,
        text=faq.answer,
        extra={
            "path": "faq_exact",
            "faq_id": faq.faq_id,
            "faq_revision": faq.revision,
            "response_class": "faq_only",
            "used_evidence_ids": [f"faq:{faq.faq_id}"],
        },
        apply_greeting=apply_greeting,
    )


async def semantic_faq_result(
    turn: CustomerTurn,
    message: str,
    channel: str,
    *,
    apply_greeting: Callable[[CustomerTurn, str, str, FinalReplyEnvelope], FinalReplyEnvelope],
) -> TurnResult | None:
    if turn.invocation_kind == "followup" or not message.strip():
        return None
    try:
        from services.ai_setup.version_store import load_published_content
        from services.brain.faq_semantic import semantic_faq_bundle

        _pointer, sections = load_published_content(turn.tenant_id)
        bundle = await semantic_faq_bundle(sections, message, tenant_id=turn.tenant_id)
    except Exception:
        return None
    if bundle.outcome == "ambiguous" or len(bundle.items) > 1:
        return None
    if bundle.outcome != "found" or len(bundle.items) != 1:
        return None
    item = bundle.items[0]
    if not faq_static_allowed(item.text, tenant_id=turn.tenant_id):
        return None
    return faq_envelope(
        turn,
        message,
        channel,
        text=item.text,
        extra={
            "path": "faq_semantic",
            "faq_id": item.source_id,
            "response_class": "faq_only",
            "used_evidence_ids": [item.evidence_id],
        },
        apply_greeting=apply_greeting,
    )
