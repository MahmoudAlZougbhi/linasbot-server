"""Information-retrieval metrics for offline Customer Brain evals."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def recall_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0
    hit = sum(1 for doc_id in ranked[:k] if doc_id in relevant)
    return hit / len(relevant)


def precision_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for doc_id in top if doc_id in relevant) / len(top)


def mrr(relevant: set[str], ranked: Sequence[str]) -> float:
    for index, doc_id in enumerate(ranked):
        if doc_id in relevant:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(relevant: set[str], ranked: Sequence[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0

    def dcg(ids: Sequence[str]) -> float:
        total = 0.0
        for index, doc_id in enumerate(ids[:k]):
            rel = 1.0 if doc_id in relevant else 0.0
            total += rel / math.log2(index + 2)
        return total

    ideal = dcg(list(relevant)[:k] if len(relevant) >= k else list(relevant))
    if ideal <= 0:
        return 0.0
    return dcg(ranked) / ideal


def mean(values: Iterable[float]) -> float:
    rows = list(values)
    if not rows:
        return 0.0
    return sum(rows) / len(rows)


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(1.0, p)) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def retrieval_row(relevant: set[str], ranked: Sequence[str]) -> dict[str, float]:
    return {
        "recall@1": recall_at_k(relevant, ranked, 1),
        "recall@3": recall_at_k(relevant, ranked, 3),
        "recall@5": recall_at_k(relevant, ranked, 5),
        "recall@10": recall_at_k(relevant, ranked, 10),
        "precision@5": precision_at_k(relevant, ranked, 5),
        "precision@10": precision_at_k(relevant, ranked, 10),
        "mrr": mrr(relevant, ranked),
        "ndcg@5": ndcg_at_k(relevant, ranked, 5),
        "ndcg@10": ndcg_at_k(relevant, ranked, 10),
    }
