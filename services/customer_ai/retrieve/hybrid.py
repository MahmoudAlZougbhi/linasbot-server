"""Fuse lexical + Voyage semantic ranks. Never average raw scores across spaces."""

from __future__ import annotations

from dataclasses import dataclass, replace

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


def _card_with_chunk(card: TitleCard, search_text: str) -> TitleCard:
    chunk = (search_text or "").strip()
    if not chunk or card.source_family != "knowledge":
        return card
    return replace(card, body=chunk)


async def _semantic_from_store(
    tenant_id: str,
    query: str,
    scoped: list[TitleCard],
    families: set[SourceFamily] | None,
    limit: int,
) -> list[tuple[float, TitleCard]] | None:
    if not tenant_id.strip():
        return None
    from services.customer_ai.search.store import query_similar

    qvec = await embed_texts(ENTITY_QUERY, [query])
    from datetime import datetime, timezone

    from services.membership.provider_expense import record_pending_provider

    record_pending_provider(
        event_id=f"embed-query:{tenant_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
        tenant_id=tenant_id,
        category="embedding",
        feature="customer_chat",
        provider="voyage",
        model=ENTITY_QUERY.model,
        operation_id="query",
    )

    def _map(result) -> list[tuple[float, TitleCard]] | None:
        if result.outcome != "found" or not result.items:
            return None
        by_id = {card.item_id: card for card in scoped}
        by_source = {card.item_id.split(":", 1)[-1]: card for card in scoped}
        mapped: list[tuple[float, TitleCard]] = []
        for hit in result.items:
            card = (
                by_id.get(hit.doc_id)
                or by_id.get(f"{hit.source_family}:{hit.source_id}")
                or by_source.get(hit.source_id)
            )
            if card is None:
                continue
            mapped.append((hit.score, _card_with_chunk(card, hit.search_text)))
        return mapped or None

    query_kwargs = {
        "tenant_id": tenant_id,
        "space_id": ENTITY_DOCUMENT.space_id,
        "vector": qvec.vectors[0],
        "families": set(families) if families else None,
        "limit": limit,
    }
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        with whatsapp_session(require=True) as session:
            mapped = _map(query_similar(session, **query_kwargs))
            if mapped is not None:
                return mapped
    except WhatsAppDatabaseUnavailable:
        pass
    except Exception:
        pass
    return _map(query_similar(None, **query_kwargs))


async def search_hybrid(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    limit: int | None = None,
    tenant_id: str = "",
) -> list[HybridHit]:
    if not compatible(ENTITY_DOCUMENT, ENTITY_QUERY):
        raise RuntimeError("entity_space_mismatch")
    cap = limit if limit is not None else DEFAULT_BUDGETS.lexical_candidates_per_source
    scoped = [c for c in cards if families is None or c.source_family in families]
    lexical = search_cards(scoped, query, families=families, limit=DEFAULT_BUDGETS.lexical_candidates_per_source)
    texts = [card.search_text for card in scoped]
    if not texts:
        return []
    stored = await _semantic_from_store(
        tenant_id,
        query,
        scoped,
        families,
        DEFAULT_BUDGETS.semantic_candidates_per_source,
    )
    if stored is None:
        semantic = []
    else:
        semantic = stored[: DEFAULT_BUDGETS.semantic_candidates_per_source]
    fused = _rrf(
        [hit.card.item_id for hit in lexical],
        [card.item_id for _score, card in semantic],
    )
    by_id = {card.item_id: card for card in scoped}
    sem_cards = {card.item_id: card for _score, card in semantic}
    lex_map = {hit.card.item_id: hit.score for hit in lexical}
    sem_map = {card.item_id: score for score, card in semantic}
    ordered = sorted(fused.items(), key=lambda row: (-row[1], row[0]))[:cap]
    out: list[HybridHit] = []
    for rank, (item_id, _score) in enumerate(ordered):
        card = sem_cards.get(item_id) or by_id.get(item_id)
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
