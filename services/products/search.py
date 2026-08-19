"""Deterministic product title search — inactive excluded from customer-facing."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.products.availability import is_customer_searchable
from services.products.repository import ProductsRepository
from services.products.schemas import normalize_product_name, product_to_dict
from services.products.search_scoring import is_confident_match, rank_products

MIN_SCORE = 0.55


def _unique_queries(*values: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        key = " ".join(text.lower().split())
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    customer_facing: bool = True,
    alternate_queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    queries = _unique_queries(title, *(alternate_queries or []))
    if not queries:
        return []

    repo = ProductsRepository(session)
    merged: dict[str, dict[str, Any]] = {}
    catalog: list[Any] | None = None

    def _catalog() -> list[Any]:
        nonlocal catalog
        if catalog is None:
            rows = repo.list_all_for_tenant(tenant_id=tenant_id, customer_facing=customer_facing)
            if customer_facing:
                rows = [row for row in rows if is_customer_searchable(row.availability)]
            catalog = rows
        return catalog

    for query_text in queries:
        query = normalize_product_name(query_text)
        if not query:
            continue
        prefix_hits = repo.search_by_title_prefix(
            tenant_id=tenant_id,
            query=query,
            limit=max(limit, 8),
            customer_facing=customer_facing,
        )
        if prefix_hits:
            ranked = rank_products(query, prefix_hits, limit=limit)
            ordered = [row for _score, row in ranked] if ranked else list(prefix_hits)
            seen_ids = {str(row.id) for row in ordered}
            for row in prefix_hits:
                if str(row.id) not in seen_ids:
                    ordered.append(row)
                    seen_ids.add(str(row.id))
            for row in ordered[:limit]:
                merged.setdefault(str(row.id), product_to_dict(row))
            continue
        scored = rank_products(query, _catalog(), limit=limit)
        for score, row in scored:
            if is_confident_match(score):
                merged.setdefault(str(row.id), product_to_dict(row))
    return list(merged.values())[:limit]


def search_product_by_title_with_scores(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    customer_facing: bool = True,
    alternate_queries: list[str] | None = None,
) -> list[tuple[float, dict[str, Any]]]:
    """Return (score, product_dict) pairs for resolution priority logic."""
    queries = _unique_queries(title, *(alternate_queries or []))
    if not queries:
        return []
    repo = ProductsRepository(session)
    candidates = repo.list_all_for_tenant(tenant_id=tenant_id, customer_facing=customer_facing)
    if customer_facing:
        candidates = [row for row in candidates if is_customer_searchable(row.availability)]
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for query_text in queries:
        query = normalize_product_name(query_text)
        if not query:
            continue
        scored = rank_products(query, candidates, limit=limit)
        for score, row in scored:
            if score < MIN_SCORE:
                continue
            current = best.get(str(row.id))
            if current is None or score > current[0]:
                best[str(row.id)] = (score, product_to_dict(row))
    ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)
    return ranked[:limit]
