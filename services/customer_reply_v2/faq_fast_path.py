"""Published FAQ fast path with context-dependent rejection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.cm.version_store import load_published_content
from services.faq_answer_localize import localize_faq_answer

# Pronouns / follow-ups that require conversation or post context — never FAQ-direct.
_CONTEXT_DEPENDENT = re.compile(
    r"(قديش\s+هيدا|قديش\s+هيدي|this\s+one|that\s+one|the\s+second|"
    r"yes,?\s+that\s+branch|نفس\s+الشي|نفسها|هيدا\s*\?|هيدي\s*\?|"
    r"how\s+much\s+is\s+(this|that)|c'?est\s+combien)",
    re.I,
)

SEMANTIC_FAQ_MIN_SCORE = 0.90


@dataclass
class FaqFastPathResult:
    hit: bool
    answer: str = ""
    reason: str = ""
    metadata: dict[str, Any] | None = None


def is_context_dependent_question(message: str) -> bool:
    return bool(_CONTEXT_DEPENDENT.search(message or ""))


async def _localized_answer(
    *,
    answer: str,
    matched_language: str | None,
    response_language: str,
    metadata: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    localized = await localize_faq_answer(
        answer=answer,
        source_language=matched_language,
        target_language=response_language,
    )
    meta = dict(metadata or {})
    if matched_language and matched_language != response_language:
        meta["matched_language"] = matched_language
        meta["response_language"] = response_language
        meta["localized"] = localized != answer
    return localized, meta or None


async def try_faq_fast_path(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str | None = None,
    has_unresolved_context_refs: bool = False,
) -> FaqFastPathResult:
    """Exact / fuzzy / high-confidence semantic FAQ. Published only. Tenant-scoped."""
    if is_context_dependent_question(message) or has_unresolved_context_refs:
        return FaqFastPathResult(hit=False, reason="context_dependent")

    visitor_language = (response_language or detected_language or "en").strip().lower()

    # Ensure published exists (raises if not).
    load_published_content(tenant_id)

    from services.local_qa_service import local_qa_service

    tiered = await local_qa_service.find_match_with_tier(message, detected_language)
    if tiered:
        qa = tiered.get("qa_pair") or {}
        answer = str(qa.get("answer") or "").strip()
        if answer:
            matched_language = str(tiered.get("matched_language") or qa.get("language") or detected_language)
            localized, meta = await _localized_answer(
                answer=answer,
                matched_language=matched_language,
                response_language=visitor_language,
                metadata={
                    "match_score": tiered.get("match_score"),
                    "tier": tiered.get("tier"),
                },
            )
            return FaqFastPathResult(
                hit=True,
                answer=localized,
                reason="faq_exact" if tiered.get("tier") == "exact" else "faq_direct",
                metadata=meta,
            )

    from services.cm.semantic_index import search as semantic_search
    from services.cm.version_store import read_published_pointer

    pointer = read_published_pointer(tenant_id)
    if not pointer or not pointer.index_version_id:
        return FaqFastPathResult(hit=False, reason="index_unavailable")

    async def _semantic_hits(*, language: str | None) -> list[dict[str, Any]]:
        try:
            return await semantic_search(
                tenant_id=tenant_id,
                index_id=pointer.index_version_id,
                query=message,
                kind="faq",
                language=language,
                top_k=2,
            )
        except Exception:
            return []

    hits = await _semantic_hits(language=detected_language)
    if not hits:
        hits = await _semantic_hits(language=None)

    if not hits:
        return FaqFastPathResult(hit=False, reason="faq_miss")

    # Ambiguous: two strong hits → do not answer directly.
    strong = [h for h in hits if float(h.get("score") or 0) >= SEMANTIC_FAQ_MIN_SCORE]
    if len(strong) >= 2:
        scores = [float(h.get("score") or 0) for h in strong[:2]]
        if abs(scores[0] - scores[1]) < 0.02:
            return FaqFastPathResult(hit=False, reason="faq_ambiguous")

    if strong:
        top = strong[0]
        metadata = top.get("metadata") or {}
        answer = str(metadata.get("answer") or "").strip()
        if answer:
            matched_language = str(metadata.get("language") or detected_language)
            localized, meta = await _localized_answer(
                answer=answer,
                matched_language=matched_language,
                response_language=visitor_language,
                metadata={
                    "match_score": top.get("score"),
                    "source_id": top.get("source_id"),
                },
            )
            return FaqFastPathResult(
                hit=True,
                answer=localized,
                reason="faq_semantic",
                metadata=meta,
            )
    return FaqFastPathResult(hit=False, reason="faq_miss")
