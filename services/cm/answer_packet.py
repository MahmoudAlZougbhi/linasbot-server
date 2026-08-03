"""Assemble the grounded answer packet (plan §12 step 13 / §12.2 / §13.1)."""

from __future__ import annotations

from typing import Any

from services.cm.schemas import AiBasics, AnswerChunk, AnswerFact, AnswerPacket, StylePolicy

#: Locked platform rules surfaced in every packet (code-level, never editable via CM draft).
PLATFORM_RULES: tuple[str, ...] = (
    "Never invent a business fact that is not present in this packet's facts/chunks.",
    "Never offer, price, or schedule a restricted service.",
    "Respond only in the packet's response_language.",
    "A WhatsApp handoff number may only be stated if it matches a packet 'handoff_phone' fact.",
)


def build_answer_packet(
    *,
    tenant_id: str,
    content_version_id: str,
    index_version_id: str | None,
    detected_language: str,
    response_language: str,
    sections: dict[str, dict[str, Any]],
    facts: list[AnswerFact] | None = None,
    chunks: list[AnswerChunk] | None = None,
    history_summary: str = "",
) -> AnswerPacket:
    """Build the grounded packet the caller's large-AI pipeline (and validator) will use."""
    ai_basics_payload = sections.get("ai_basics") or {}
    style_payload = sections.get("style") or {}
    identity = AiBasics.model_validate(ai_basics_payload) if ai_basics_payload else AiBasics()
    style = StylePolicy.model_validate(style_payload) if style_payload else StylePolicy()

    fact_list = list(facts or [])
    chunk_list = list(chunks or [])
    source_ids = sorted({fact.source_id for fact in fact_list} | {chunk.source_id for chunk in chunk_list})

    return AnswerPacket(
        tenant_id=tenant_id,
        content_version_id=content_version_id,
        index_version_id=index_version_id,
        detected_language=detected_language,
        response_language=response_language,
        identity=identity,
        style=style,
        facts=fact_list,
        chunks=chunk_list,
        source_ids=source_ids,
        platform_rules=list(PLATFORM_RULES),
        history_summary=history_summary,
    )
