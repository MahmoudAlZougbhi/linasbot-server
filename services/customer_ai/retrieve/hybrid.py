"""Fuse lexical + Voyage semantic ranks. Never average raw scores across spaces."""

from __future__ import annotations

from dataclasses import dataclass

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.providers.spaces import ENTITY_DOCUMENT, ENTITY_QUERY, compatible
from services.customer_ai.providers.voyage_client import embed_texts
from services.customer_ai.retrieve.cards import TitleCard
from services.customer_ai.retrieve.lexical import search_cards


@dataclass(frozen=True)
class HybridHit:
    card: TitleCard
    lexical_score: float
    semantic_score: float
    fused_rank: int


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    n1 = sum(a * a for a in left) ** 0.5
    n2 = sum(b * b for b in right) ** 0.5
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _rrf(*rank_lists: list[str], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for index, item_id in enumerate(ranks):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + index + 1)
    return scores


async def search_hybrid(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    limit: int | None = None,
) -> list[HybridHit]:
    if not compatible(ENTITY_DOCUMENT, ENTITY_QUERY):
        raise RuntimeError("entity_space_mismatch")
    cap = limit if limit is not None else DEFAULT_BUDGETS.lexical_candidates_per_source
    scoped = [c for c in cards if families is None or c.source_family in families]
    lexical = search_cards(scoped, query, families=families, limit=DEFAULT_BUDGETS.lexical_candidates_per_source)
    texts = [card.search_text for card in scoped]
    if not texts:
        return []
    docs = await embed_texts(ENTITY_DOCUMENT, texts)
    qvec = await embed_texts(ENTITY_QUERY, [query])
    query_vec = qvec.vectors[0]
    semantic: list[tuple[float, TitleCard]] = []
    for card, vector in zip(scoped, docs.vectors, strict=True):
        semantic.append((_cosine(query_vec, vector), card))
    semantic.sort(key=lambda row: (-row[0], row[1].item_id))
    semantic = semantic[: DEFAULT_BUDGETS.semantic_candidates_per_source]
    fused = _rrf(
        [hit.card.item_id for hit in lexical],
        [card.item_id for _score, card in semantic],
    )
    by_id = {card.item_id: card for card in scoped}
    lex_map = {hit.card.item_id: hit.score for hit in lexical}
    sem_map = {card.item_id: score for score, card in semantic}
    ordered = sorted(fused.items(), key=lambda row: (-row[1], row[0]))[:cap]
    out: list[HybridHit] = []
    for rank, (item_id, _score) in enumerate(ordered):
        card = by_id.get(item_id)
        if card is None:
            continue
        out.append(
            HybridHit(
                card=card,
                lexical_score=lex_map.get(item_id, 0.0),
                semantic_score=sem_map.get(item_id, 0.0),
                fused_rank=rank,
            )
        )
    return out
