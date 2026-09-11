"""Okapi BM25 lexical search over published title cards.

Scoring is real BM25 (term saturation + length normalization + idf) computed over the scoped
card set, not substring matching. Scores are unbounded, so consumers must compare ranks (see
retrieve/hybrid.py RRF) and never treat a score as a probability or an exact-match signal.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.normalize import normalize_search_text
from services.customer_ai.retrieve.cards import TitleCard
from services.customer_ai.retrieve.normalize_ar import normalize_arabic

BM25_K1 = 1.5
BM25_B = 0.75


@dataclass(frozen=True)
class LexicalHit:
    card: TitleCard
    score: float


def prepare_query_text(query: str) -> str:
    """Normalize query; fold Arabic/Arabizi and expand retrieval synonyms."""
    import re

    from services.customer_ai.agent.normalize_query import normalize_query

    norm = normalize_query(query)
    parts = [norm.get("primary") or "", *(norm.get("alternates") or [])[:2], query]
    base = normalize_search_text(" ".join(p for p in parts if p))
    if re.search(r"(دوام|اوقات|أوقات|ساعات|aw2at|dawem|hours|open(?:ing)?)", base, re.I):
        base = normalize_search_text(f"{base} hours opening clinic hours")
    folded = normalize_arabic(base)
    if folded and folded not in base:
        return normalize_search_text(f"{base} {folded}")
    return base


def tokenize(text: str) -> list[str]:
    return [token for token in (text or "").split() if token]


def _idf(total_docs: int, doc_freq: int) -> float:
    """Okapi idf with the +1 smoothing that keeps common terms positive instead of negative."""
    return math.log(1.0 + ((total_docs - doc_freq + 0.5) / (doc_freq + 0.5)))


def bm25_scores(query_tokens: list[str], documents: list[list[str]]) -> list[float]:
    total = len(documents)
    if not total or not query_tokens:
        return [0.0] * total
    lengths = [len(doc) for doc in documents]
    avg_len = (sum(lengths) / total) or 1.0
    counts = [Counter(doc) for doc in documents]
    terms = list(dict.fromkeys(query_tokens))
    doc_freq = {term: sum(1 for count in counts if term in count) for term in terms}
    idf = {term: _idf(total, doc_freq[term]) for term in terms if doc_freq[term]}
    scores: list[float] = []
    for index, count in enumerate(counts):
        norm = BM25_K1 * (1.0 - BM25_B + (BM25_B * (lengths[index] / avg_len)))
        score = 0.0
        for term, weight in idf.items():
            freq = count.get(term, 0)
            if not freq:
                continue
            score += weight * ((freq * (BM25_K1 + 1.0)) / (freq + norm))
        scores.append(score)
    return scores


def search_cards(
    cards: list[TitleCard],
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    limit: int | None = None,
) -> list[LexicalHit]:
    cap = limit if limit is not None else DEFAULT_BUDGETS.lexical_candidates_per_source
    scoped = [card for card in cards if families is None or card.source_family in families]
    query_tokens = tokenize(prepare_query_text(query))
    if not scoped or not query_tokens:
        return []
    scores = bm25_scores(
        query_tokens,
        [tokenize(prepare_query_text(card.search_text)) for card in scoped],
    )
    hits = [LexicalHit(card=card, score=score) for card, score in zip(scoped, scores, strict=True) if score > 0]
    hits.sort(key=lambda item: (-item.score, item.card.item_id))
    return hits[:cap]
