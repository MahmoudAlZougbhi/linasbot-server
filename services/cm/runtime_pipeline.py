"""Canonical published-mode runtime pipeline (plan §12). Exact order, no silent fallback.

Order implemented here: load published version → (language is caller-provided) → platform
rules → restricted → handoff (only if not restricted) → exact FAQ → semantic FAQ → (hit:
return, skip Interpreter/generative) → Query Interpreter (FAQ miss only) → structured facts →
bounded semantic chunks → answer packet → (CALLER runs the existing large-AI pipeline) →
validate → at most one constrained regeneration → re-validate → honest failure message.

This module never sends messages and never mutates production/customer history. It is pure
orchestration over read-only CM state plus the injected ``regenerate_fn`` callback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from services.cm.answer_packet import build_answer_packet
from services.cm.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY
from services.cm.embeddings import HashEmbeddingForbiddenError, PublishedEmbeddingError, assert_published_embedding_pin
from services.cm.query_interpreter import BOOKING_INTENT_RE, HUMAN_INTENT_RE, InterpretedQuery, interpret_query
from services.cm.response_validator import ValidationResult, validate_response
from services.cm.schemas import AnswerChunk, AnswerFact, AnswerPacket, HandoffPolicy, RestrictedPolicy, ServicesSection
from services.cm.semantic_index import search as semantic_search
from services.cm.structured_resolver import (
    active_restricted_ids,
    find_restricted_topic,
    resolve_branch_facts,
    resolve_handoff,
    resolve_price_facts,
    resolve_service_facts,
)
from services.cm.version_store import PublishedVersionError, load_published_content
from services.dynamic_messages_service import get_dynamic_message
from services.local_qa_service import local_qa_service

RegenerateFn = Callable[[str, list[str]], Awaitable[str]]

SEMANTIC_FAQ_MIN_SCORE = 0.90


@dataclass
class PipelineOutcome:
    """Result of :func:`prepare_response`. ``stop=True`` means ``reply`` is final (send as-is)."""

    stop: bool
    reply: str | None = None
    reason: str = ""
    packet: AnswerPacket | None = None
    interpreted: InterpretedQuery | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


DEFAULT_REFUSE_TEMPLATES: dict[str, str] = {
    "ar": "هيدا الموضوع مش من ضمن الخدمات يلي منقدمها حالياً. بس فيني ساعدك بمواضيع تانية.",
    "en": "This isn't one of the services we currently offer, but I'm happy to help with anything else.",
    "fr": "Ce sujet ne fait pas partie des services que nous proposons actuellement, mais je peux vous aider pour autre chose.",
}

_HANDOFF_TEMPLATES: dict[str, str] = {
    "ar": "للحجز أو للتواصل مع فريقنا، تواصل معنا على واتساب فقط:\n{phone}\nhttps://wa.me/{digits}",
    "en": "For booking or to reach our team, please contact us on WhatsApp only:\n{phone}\nhttps://wa.me/{digits}",
    "fr": "Pour réserver ou contacter notre équipe, écrivez-nous uniquement sur WhatsApp :\n{phone}\nhttps://wa.me/{digits}",
}


def _refuse_reply(topic: Any, response_language: str) -> str:
    template = (getattr(topic, "refuse_template", "") or "").strip()
    if template:
        return template
    return DEFAULT_REFUSE_TEMPLATES.get(response_language, DEFAULT_REFUSE_TEMPLATES["en"])


def _handoff_reply(phone: str, response_language: str) -> str:
    template = _HANDOFF_TEMPLATES.get(response_language, _HANDOFF_TEMPLATES["en"])
    digits = "".join(ch for ch in phone if ch.isdigit())
    return template.format(phone=phone, digits=digits)


def _detect_booking_or_human(message: str) -> str | None:
    """Deterministic-only pre-FAQ check (plan §12 step 6). Deliberately NOT the Interpreter."""
    if HUMAN_INTENT_RE.search(message or ""):
        return "human"
    if BOOKING_INTENT_RE.search(message or ""):
        return "booking"
    return None


async def prepare_response(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str,
) -> PipelineOutcome:
    """Run plan §12 steps 2–13. Returns a final reply (stop=True) or a packet to run AI on."""
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError as exc:
        return PipelineOutcome(stop=True, reason="no_published_version", error=str(exc))

    try:
        assert_published_embedding_pin(pointer.embedding_provider, context="pointer")
    except PublishedEmbeddingError as exc:
        return PipelineOutcome(stop=True, reason="invalid_published_embedding", error=str(exc))

    restricted_policy = RestrictedPolicy.model_validate(sections.get("restricted") or {})
    handoff_policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
    services_section = ServicesSection.model_validate(sections.get("services") or {})
    restricted_ids = active_restricted_ids(restricted_policy)

    # Step 5 — Restricted. Never proceeds to handoff/booking (plan §12.1 / T23).
    restricted_topic = find_restricted_topic(message, restricted_policy)
    if restricted_topic is not None:
        return PipelineOutcome(
            stop=True,
            reply=_refuse_reply(restricted_topic, response_language),
            reason="restricted",
            metadata={"restricted_topic_id": restricted_topic.id},
        )

    # Step 6 — Handoff only for explicit booking/human intent, only if not restricted.
    handoff_intent = _detect_booking_or_human(message)
    if handoff_intent:
        resolution = resolve_handoff(handoff_policy)
        if resolution.contact_phone_e164:
            return PipelineOutcome(
                stop=True,
                reply=_handoff_reply(resolution.contact_phone_e164, response_language),
                reason="handoff",
                metadata={"handoff_intent": handoff_intent, "matched_row_id": resolution.matched_row_id},
            )
        # No confidently-resolvable contact — fall through rather than invent a number.

    # Steps 7–9 — Exact then semantic FAQ. A hit skips the Interpreter and the generative call.
    tiered_match = await local_qa_service.find_match_with_tier(message, detected_language)
    if tiered_match:
        qa_pair = tiered_match.get("qa_pair") or {}
        tier = tiered_match.get("tier") or "direct"
        return PipelineOutcome(
            stop=True,
            reply=str(qa_pair.get("answer") or ""),
            reason="faq_exact" if tier == "exact" else "faq_direct",
            metadata={"match_score": tiered_match.get("match_score"), "tier": tier},
        )

    index_id = pointer.index_version_id
    if not index_id:
        return PipelineOutcome(
            stop=True,
            reason="index_unavailable",
            error="Published pointer has no index_version_id; refusing silent legacy/keyword fallback.",
        )

    try:
        semantic_hits = await semantic_search(
            tenant_id=tenant_id, index_id=index_id, query=message, kind="faq", language=detected_language, top_k=1
        )
    except (FileNotFoundError, ValueError, KeyError, HashEmbeddingForbiddenError, PublishedEmbeddingError) as exc:
        return PipelineOutcome(stop=True, reason="index_unavailable", error=str(exc))

    if semantic_hits and float(semantic_hits[0].get("score") or 0) >= SEMANTIC_FAQ_MIN_SCORE:
        top = semantic_hits[0]
        answer = str((top.get("metadata") or {}).get("answer") or "")
        if answer:
            return PipelineOutcome(
                stop=True,
                reply=answer,
                reason="faq_semantic",
                metadata={"match_score": top.get("score"), "source_id": top.get("source_id")},
            )

    # Step 10 — Query Interpreter runs ONLY now, on FAQ miss (T21/T31).
    interpreted = await interpret_query(message, services=services_section, restricted=restricted_policy)

    # Step 11 — Structured facts from the published version.
    facts: list[AnswerFact] = []
    if interpreted.service_id:
        facts.extend(resolve_service_facts(services_section, interpreted.service_id))
        facts.extend(resolve_price_facts(sections.get("prices") or {}, interpreted.service_id))
    if interpreted.branch_id:
        facts.extend(resolve_branch_facts(sections.get("branches") or {}, interpreted.branch_id))

    # Step 12 — Bounded semantic narrative chunks (Knowledge/Care only; never restricted-only FAQ).
    chunks: list[AnswerChunk] = []
    try:
        for kind in ("knowledge", "care"):
            hits = await semantic_search(tenant_id=tenant_id, index_id=index_id, query=message, kind=kind, top_k=2)
            for hit in hits:
                chunks.append(
                    AnswerChunk(source_id=hit["source_id"], text=str(hit.get("text") or ""), score=hit.get("score"))
                )
    except (FileNotFoundError, ValueError, KeyError, HashEmbeddingForbiddenError, PublishedEmbeddingError) as exc:
        return PipelineOutcome(stop=True, reason="index_unavailable", error=str(exc))

    # Step 13 — Assemble the grounded packet for the caller's existing large-AI pipeline.
    packet = build_answer_packet(
        tenant_id=tenant_id,
        content_version_id=pointer.content_version_id,
        index_version_id=index_id,
        detected_language=detected_language,
        response_language=response_language,
        sections=sections,
        facts=facts,
        chunks=chunks,
    )

    return PipelineOutcome(
        stop=False,
        packet=packet,
        interpreted=interpreted,
        reason="packet_ready",
        metadata={"restricted_topic_active_ids": sorted(restricted_ids)},
    )


@dataclass
class FinalizeResult:
    text: str
    ok: bool
    failed_rules: list[str] = field(default_factory=list)
    regenerated: bool = False


async def finalize_response(
    *,
    candidate_text: str,
    packet: AnswerPacket,
    restricted_topic_active_ids: set[str] | None = None,
    regenerate_fn: RegenerateFn | None = None,
) -> FinalizeResult:
    """Validate → at most one constrained regeneration → re-validate → honest failure path."""
    result = validate_response(candidate_text, packet, restricted_topic_active_ids=restricted_topic_active_ids)
    if result.ok:
        return FinalizeResult(text=candidate_text, ok=True)

    regenerated = False
    if regenerate_fn is not None:
        try:
            regenerated_text = await regenerate_fn(candidate_text, list(result.failed_rules))
        except Exception:
            regenerated_text = None
        if regenerated_text:
            regenerated = True
            result = validate_response(
                regenerated_text, packet, restricted_topic_active_ids=restricted_topic_active_ids
            )
            if result.ok:
                return FinalizeResult(text=regenerated_text, ok=True, regenerated=True)

    _emit_validation_failed_event(packet, result)
    failure_text = get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, packet.response_language)
    return FinalizeResult(text=failure_text, ok=False, failed_rules=result.failed_rules, regenerated=regenerated)


def _emit_validation_failed_event(packet: AnswerPacket, result: ValidationResult) -> None:
    """PII-safe event: tenant + content/index version + failed rule IDs only — never message text."""
    print(
        "[cm.runtime_pipeline] event=answer_validation_failed "
        f"tenant_id={packet.tenant_id} content_version_id={packet.content_version_id} "
        f"index_version_id={packet.index_version_id} failed_rules={result.failed_rules}"
    )
