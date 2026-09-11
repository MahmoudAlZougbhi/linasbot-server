"""Exact / semantic FAQ turn envelopes for the DM pipeline."""

from __future__ import annotations

from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.faq_exact import find_published_exact_faq
from services.customer_ai.faq_freshness import faq_static_allowed
from services.customer_ai.templates import brain_template


def _destination(channel: str) -> str:
    return "web_chat" if "web" in (channel or "") else "dm"


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


def faq_envelope(
    turn: CustomerTurn,
    message: str,
    channel: str,
    *,
    text: str,
    extra: dict,
    apply_greeting,
) -> TurnResult:
    destination = _destination(channel)
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


def exact_faq_result(turn: CustomerTurn, message: str, channel: str, *, apply_greeting) -> TurnResult | None:
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
    apply_greeting,
) -> TurnResult | None:
    if turn.invocation_kind == "followup" or not message.strip():
        return None
    try:
        from services.cm.version_store import load_published_content
        from services.customer_ai.faq_semantic import semantic_faq_bundle

        _pointer, sections = load_published_content(turn.tenant_id)
        bundle = await semantic_faq_bundle(sections, message, tenant_id=turn.tenant_id)
    except Exception:
        return None
    lang = _response_language(turn)
    if bundle.outcome == "ambiguous" or len(bundle.items) > 1:
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="clarify",
                messages=[
                    OutboundMessage(
                        destination=_destination(channel),
                        text=brain_template("faq_ambiguous", lang),
                    )
                ],
            ),
            extra={
                "path": "faq_semantic",
                "faq_outcome": "ambiguous",
                "response_class": "operational_notice",
                "ambiguities": list(bundle.ambiguities),
            },
        )
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
