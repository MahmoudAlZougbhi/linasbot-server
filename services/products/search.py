"""Deterministic product title search — inactive excluded from customer-facing."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.products.availability import is_customer_searchable
from services.products.repository import ProductsRepository
from services.products.schemas import normalize_product_name, product_to_dict
from services.products.search_scoring import is_confident_match, rank_products

MIN_SCORE = 0.55


def search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    customer_facing: bool = True,
) -> list[dict[str, Any]]:
    query = normalize_product_name(title)
    if not query:
        return []

    repo = ProductsRepository(session)
    prefix_hits = repo.search_by_title_prefix(
        tenant_id=tenant_id,
        query=query,
        limit=limit,
        customer_facing=customer_facing,
    )
    if prefix_hits:
        return [product_to_dict(row) for row in prefix_hits[:limit]]

    candidates = repo.list_all_for_tenant(tenant_id=tenant_id, customer_facing=customer_facing)
    if customer_facing:
        candidates = [row for row in candidates if is_customer_searchable(row.availability)]
    scored = rank_products(query, candidates, limit=limit)
    return [product_to_dict(row) for score, row in scored if is_confident_match(score)]


def search_product_by_title_with_scores(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
    customer_facing: bool = True,
) -> list[tuple[float, dict[str, Any]]]:
    """Return (score, product_dict) pairs for resolution priority logic."""
    query = normalize_product_name(title)
    if not query:
        return []
    repo = ProductsRepository(session)
    candidates = repo.list_all_for_tenant(tenant_id=tenant_id, customer_facing=customer_facing)
    if customer_facing:
        candidates = [row for row in candidates if is_customer_searchable(row.availability)]
    scored = rank_products(query, candidates, limit=limit)
    return [(score, product_to_dict(row)) for score, row in scored if score >= MIN_SCORE]
