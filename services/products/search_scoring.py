"""Scoring helpers for deterministic product title search."""

from __future__ import annotations

import difflib
import re
from typing import Any

MIN_SCORE = 0.55
TOKEN_MIN_SCORE = 0.45


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\W_]+", text.lower()) if t]


def _trigrams(text: str) -> set[str]:
    padded = f"  {text}  "
    return {padded[i : i + 3] for i in range(max(len(padded) - 2, 0))}


def trigram_similarity(left: str, right: str) -> float:
    a = _trigrams(left)
    b = _trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def token_overlap_score(query: str, candidate: str) -> float:
    q_tokens = _tokens(query)
    c_tokens = _tokens(candidate)
    if not q_tokens or not c_tokens:
        return 0.0
    q_set = set(q_tokens)
    c_set = set(c_tokens)
    overlap = len(q_set & c_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(q_set)
    recall = overlap / len(c_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_product_name(query: str, candidate_normalized: str, candidate_raw: str = "") -> float:
    if not query or not candidate_normalized:
        return 0.0
    if query == candidate_normalized:
        return 1.0
    if query in candidate_normalized or candidate_normalized in query:
        return 0.92
    seq = difflib.SequenceMatcher(None, query, candidate_normalized).ratio()
    token = token_overlap_score(query, candidate_normalized)
    tri = trigram_similarity(query, candidate_normalized)
    raw_token = token_overlap_score(query, candidate_raw) if candidate_raw else 0.0
    return max(seq, token, tri, raw_token)


def is_confident_match(score: float) -> bool:
    return score >= MIN_SCORE


def product_search_blob(row: Any) -> str:
    keywords = getattr(row, "ai_search_keywords", None) or []
    if not isinstance(keywords, list):
        keywords = []
    parts = [
        str(getattr(row, "name", "") or ""),
        str(getattr(row, "name_normalized", "") or ""),
        str(getattr(row, "description", "") or ""),
        str(getattr(row, "description_normalized", "") or ""),
        str(getattr(row, "ai_search_title", "") or ""),
        str(getattr(row, "ai_search_description", "") or ""),
        " ".join(str(k) for k in keywords if str(k).strip()),
        str(getattr(row, "note", "") or ""),
    ]
    return " ".join(p for p in parts if p)


def rank_products(
    query: str,
    rows: list[Any],
    *,
    limit: int = 5,
) -> list[tuple[float, Any]]:
    scored: list[tuple[float, Any]] = []
    for row in rows:
        name_score = score_product_name(query, str(row.name_normalized or ""), str(row.name or ""))
        blob = product_search_blob(row)
        blob_norm = " ".join(blob.lower().split())
        blob_score = score_product_name(query, blob_norm, blob) if blob_norm else 0.0
        score = max(name_score, blob_score)
        if score >= TOKEN_MIN_SCORE:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]
