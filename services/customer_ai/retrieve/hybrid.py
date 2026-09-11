"""Fuse lexical + Voyage semantic ranks. Never average raw scores across spaces."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.providers.spaces import (
    ENTITY_DOCUMENT,
    ENTITY_QUERY,
    KNOWLEDGE_DOCUMENT,
    KNOWLEDGE_QUERY,
    compatible,
)
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
    *,
    operation_id: str = "",
) -> list[tuple[float, TitleCard]] | None:
    if not tenant_id.strip():
        return None
    from services.customer_ai.search.store import query_similar

    use_knowledge = families is None or bool({"knowledge", "care", "faq"} & set(families or set()))
    query_space = KNOWLEDGE_QUERY if use_knowledge and compatible(KNOWLEDGE_DOCUMENT, KNOWLEDGE_QUERY) else ENTITY_QUERY
    doc_space = KNOWLEDGE_DOCUMENT if query_space is KNOWLEDGE_QUERY else ENTITY_DOCUMENT
    # Prefer contextual knowledge space when available; always also try entity for services/products.
    spaces = [(doc_space, query_space)]
    if use_knowledge and doc_space is KNOWLEDGE_DOCUMENT:
        spaces.append((ENTITY_DOCUMENT, ENTITY_QUERY))

    from datetime import datetime

    from services.membership.provider_expense import record_pending_provider

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

    merged: list[tuple[float, TitleCard]] = []
    seen: set[str] = set()
    for doc_space_i, query_space_i in spaces:
        try:
            if query_space_i.endpoint == "contextualized":
                from services.customer_ai.providers.voyage_client import embed_contextual_groups

                groups = await embed_contextual_groups(query_space_i, [[query]])
                qvec_vectors = groups[0].vectors if groups else []
                if not qvec_vectors:
                    raise RuntimeError("empty_contextual_query")
                q_vector = qvec_vectors[0]
                q_model = query_space_i.model
            else:
                qvec = await embed_texts(query_space_i, [query])
                q_vector = qvec.vectors[0]
                q_model = query_space_i.model
        except Exception:
            if doc_space_i is ENTITY_DOCUMENT:
                continue
            try:
                qvec = await embed_texts(ENTITY_QUERY, [query])
                doc_space_i = ENTITY_DOCUMENT
                q_vector = qvec.vectors[0]
                q_model = ENTITY_QUERY.model
            except Exception:
                continue
        record_pending_provider(
            event_id=f"embed-query:{tenant_id}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
            tenant_id=tenant_id,
            category="embedding",
            feature="customer_chat",
            provider="voyage",
            model=q_model,
            operation_id=(operation_id or "query").strip() or "query",
        )
        query_kwargs = {
            "tenant_id": tenant_id,
            "space_id": doc_space_i.space_id,
            "vector": q_vector,
            "families": set(families) if families else None,
            "limit": limit,
        }
        mapped = None
        try:
            from db.session import whatsapp_session

            with whatsapp_session(require=True) as session:
                mapped = _map(query_similar(session, **query_kwargs))
        except Exception:
            mapped = _map(query_similar(None, **query_kwargs))
        if not mapped:
            continue
        for score, card in mapped:
            if card.item_id in seen:
                continue
            seen.add(card.item_id)
            merged.append((score, card))
        if merged and doc_space_i is KNOWLEDGE_DOCUMENT:
            break
    return merged or None


async def search_hybrid(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    limit: int | None = None,
    tenant_id: str = "",
    operation_id: str = "",
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
        operation_id=operation_id,
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
