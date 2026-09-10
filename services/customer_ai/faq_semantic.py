"""Semantic FAQ after exact match. Close-but-wrong answers stay out."""

from __future__ import annotations

from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.faq_exact import faq_fast_path_safe
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.orchestrate import retrieve_cards


async def semantic_faq_bundle(sections: dict, query: str) -> EvidenceBundle:
    if not faq_fast_path_safe(query):
        return EvidenceBundle(outcome="not_found")
    cards = [card for card in cards_from_sections(sections) if card.source_family == "faq"]
    if not cards:
        return EvidenceBundle(outcome="not_found")
    bundle = await retrieve_cards(cards, query, families={"faq"}, sections=sections)
    if len(bundle.items) != 1:
        if len(bundle.items) > 1:
            return EvidenceBundle(outcome="ambiguous", ambiguities=[item.evidence_id for item in bundle.items])
        return bundle
    return bundle
