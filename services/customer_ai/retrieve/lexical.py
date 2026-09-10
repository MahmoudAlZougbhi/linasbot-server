"""Lexical / fuzzy title-card search (not BM25; Postgres FTS comes later)."""

from __future__ import annotations

from dataclasses import dataclass

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.normalize import normalize_search_text
from services.customer_ai.retrieve.cards import TitleCard


@dataclass(frozen=True)
class LexicalHit:
    card: TitleCard
    score: float


def _score(query: str, card: TitleCard) -> float:
    if not query:
        return 0.0
    hay = card.search_text
    if query == hay:
        return 1.0
    if query in hay:
        return 0.85
    q_tokens = set(query.split())
    h_tokens = set(hay.split())
    if not q_tokens or not h_tokens:
        return 0.0
    overlap = len(q_tokens & h_tokens) / len(q_tokens)
    if overlap <= 0:
        return 0.0
    return 0.4 + (0.4 * overlap)


def search_cards(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    limit: int | None = None,
) -> list[LexicalHit]:
    needle = normalize_search_text(query)
    cap = limit if limit is not None else DEFAULT_BUDGETS.lexical_candidates_per_source
    hits: list[LexicalHit] = []
    for card in cards:
        if families is not None and card.source_family not in families:
            continue
        score = _score(needle, card)
        if score > 0:
            hits.append(LexicalHit(card=card, score=score))
    hits.sort(key=lambda item: (-item.score, item.card.item_id))
    return hits[:cap]
