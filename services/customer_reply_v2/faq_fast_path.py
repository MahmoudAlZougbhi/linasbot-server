"""Published FAQ fast path with context-dependent rejection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.cm.version_store import load_published_content

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


async def try_faq_fast_path(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    has_unresolved_context_refs: bool = False,
) -> FaqFastPathResult:
    """Exact / fuzzy / high-confidence semantic FAQ. Published only. Tenant-scoped."""
    if is_context_dependent_question(message) or has_unresolved_context_refs:
        return FaqFastPathResult(hit=False, reason="context_dependent")

    # Ensure published exists (raises if not).
    load_published_content(tenant_id)

    from services.local_qa_service import local_qa_service

    tiered = await local_qa_service.find_match_with_tier(message, detected_language)
    if tiered:
        qa = tiered.get("qa_pair") or {}
        answer = str(qa.get("answer") or "").strip()
        if answer:
            return FaqFastPathResult(
                hit=True,
                answer=answer,
                reason="faq_exact" if tiered.get("tier") == "exact" else "faq_direct",
                metadata={"match_score": tiered.get("match_score"), "tier": tiered.get("tier")},
            )

    from services.cm.semantic_index import search as semantic_search
    from services.cm.version_store import read_published_pointer

    pointer = read_published_pointer(tenant_id)
    if not pointer or not pointer.index_version_id:
        return FaqFastPathResult(hit=False, reason="index_unavailable")

    try:
        hits = await semantic_search(
            tenant_id=tenant_id,
            index_id=pointer.index_version_id,
            query=message,
            kind="faq",
            language=detected_language,
            top_k=2,
        )
    except Exception:
        return FaqFastPathResult(hit=False, reason="semantic_faq_error")

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
        answer = str((top.get("metadata") or {}).get("answer") or "").strip()
        if answer:
            return FaqFastPathResult(
                hit=True,
                answer=answer,
                reason="faq_semantic",
                metadata={"match_score": top.get("score"), "source_id": top.get("source_id")},
            )
    return FaqFastPathResult(hit=False, reason="faq_miss")
