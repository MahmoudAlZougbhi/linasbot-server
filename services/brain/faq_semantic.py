"""Semantic FAQ after exact match. Close-but-wrong answers stay out.

Ambiguous multi-hit results never auto-answer — callers must clarify.
"""

from __future__ import annotations

from services.brain.contracts.evidence import EvidenceBundle
from services.brain.faq_exact import faq_fast_path_safe
from services.brain.retrieve.cards import cards_from_sections
from services.brain.retrieve.orchestrate import retrieve_cards


async def semantic_faq_bundle(sections: dict, query: str, *, tenant_id: str = "") -> EvidenceBundle:
    if not faq_fast_path_safe(query):
        return EvidenceBundle(outcome="not_found")
    cards = [card for card in cards_from_sections(sections) if card.source_family == "faq"]
    if not cards:
        return EvidenceBundle(outcome="not_found")
    bundle = await retrieve_cards(cards, query, families={"faq"}, sections=sections, tenant_id=tenant_id)
    if len(bundle.items) > 1:
        # Fail closed: never pick one FAQ when several remain plausible.
        return EvidenceBundle(
            outcome="ambiguous",
            ambiguities=[item.evidence_id for item in bundle.items],
        )
    if len(bundle.items) != 1:
        return bundle
    item = bundle.items[0]
    from services.brain.entity_identity import score_label

    title_score = score_label(query, item.title)
    lexical = float((item.extra or {}).get("lexical_score") or 0.0)
    if title_score < 62.0 and lexical < 0.35:
        return EvidenceBundle(outcome="not_found")
    return bundle
