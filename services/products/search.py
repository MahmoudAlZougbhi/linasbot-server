"""Deterministic product title search (Phase 1 — basic fuzzy, no full catalog to AI)."""

from __future__ import annotations

import difflib
from typing import Any

from sqlalchemy.orm import Session

from services.products.repository import ProductsRepository
from services.products.schemas import normalize_product_name, product_to_dict

# Phase 2 will add Luna resolver + vector image matching; this module stays deterministic.
MIN_SCORE = 0.55


def search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search tenant catalog by title. Never returns full catalog — capped results only."""
    query = normalize_product_name(title)
    if not query:
        return []

    repo = ProductsRepository(session)
    prefix_hits = repo.search_by_title_prefix(tenant_id=tenant_id, query=query, limit=limit)
    if prefix_hits:
        return [product_to_dict(row) for row in prefix_hits[:limit]]

    # Fuzzy fallback over tenant products (still bounded; not sent to LLM as bulk context).
    candidates = repo.list_all_for_tenant(tenant_id=tenant_id)
    scored: list[tuple[float, Any]] = []
    for row in candidates:
        ratio = difflib.SequenceMatcher(None, query, row.name_normalized).ratio()
        if ratio >= MIN_SCORE:
            scored.append((ratio, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [product_to_dict(row) for _, row in scored[:limit]]
