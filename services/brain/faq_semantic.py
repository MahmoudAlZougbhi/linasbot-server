"""Semantic FAQ is the ≥0.90 question-embedding gate. No soft lexical fallback."""

from __future__ import annotations

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.faq_embed import FAQ_COSINE_MIN, embed_faq_query, pick_faq_embed_winner, query_faq_hits
from services.brain.faq_exact import faq_fast_path_safe, published_faq_entry


async def semantic_faq_bundle(sections: dict, query: str, *, tenant_id: str = "") -> EvidenceBundle:
    """Live DM uses faq_embed_result. This wrapper keeps the same 0.90 contract."""
    _ = sections
    tid = (tenant_id or "").strip()
    if not faq_fast_path_safe(query) or not tid:
        return EvidenceBundle(outcome="not_found")
    vector = await embed_faq_query(query)
    if not vector:
        return EvidenceBundle(outcome="not_found")
    outcome, winner = pick_faq_embed_winner(query_faq_hits(tid, vector))
    if outcome == "ambiguous":
        return EvidenceBundle(outcome="ambiguous")
    if outcome != "found" or winner is None:
        return EvidenceBundle(outcome="not_found")
    entry = published_faq_entry(tid, winner.source_id) or {}
    answer = str(entry.get("answer") or "").strip()
    if not answer:
        return EvidenceBundle(outcome="not_found")
    return EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id=f"faq:{winner.source_id}",
                source_family="faq",
                source_id=winner.source_id,
                title=str(entry.get("question") or winner.title),
                text=answer,
                extra={"faq_cosine": float(winner.score), "path": "faq_embed_90", "min": FAQ_COSINE_MIN},
            )
        ],
    )
