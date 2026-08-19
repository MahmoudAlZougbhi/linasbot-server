"""Active product titles for Luna fallback inside the same retrieval loop."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.products.availability import is_customer_searchable
from services.products.repository import ProductsRepository

TITLE_PAGE_SIZE = 80


def list_active_product_titles(
    session: Session,
    *,
    tenant_id: str,
    offset: int = 0,
    limit: int = TITLE_PAGE_SIZE,
) -> dict[str, Any]:
    start = max(0, int(offset))
    size = max(1, min(int(limit or TITLE_PAGE_SIZE), TITLE_PAGE_SIZE))
    rows = ProductsRepository(session).list_all_for_tenant(tenant_id=tenant_id, customer_facing=True)
    titles = [
        {
            "id": row.id,
            "title": row.name,
            "original_title": row.name,
            "description": str(getattr(row, "description", "") or "")[:180],
            "ai_search_title": str(getattr(row, "ai_search_title", "") or ""),
            "ai_search_description": str(getattr(row, "ai_search_description", "") or ""),
            "ai_search_keywords": list(getattr(row, "ai_search_keywords", None) or [])[:8],
            "status": str(row.availability or ""),
        }
        for row in rows
        if is_customer_searchable(row.availability)
    ]
    page = titles[start : start + size]
    next_offset = start + len(page)
    return {
        "titles": page,
        "offset": start,
        "limit": size,
        "returned": len(page),
        "total": len(titles),
        "has_more": next_offset < len(titles),
        "next_offset": next_offset if next_offset < len(titles) else None,
    }


def slim_product_match(product: Any) -> dict[str, Any]:
    if product is None:
        return {}
    if not isinstance(product, dict):
        keywords = getattr(product, "ai_search_keywords", None) or []
        return {
            "id": getattr(product, "id", None),
            "title": getattr(product, "name", None),
            "name": getattr(product, "name", None),
            "original_title": getattr(product, "name", None),
            "description": getattr(product, "description", None),
            "ai_search_title": getattr(product, "ai_search_title", None),
            "ai_search_description": getattr(product, "ai_search_description", None),
            "ai_search_keywords": list(keywords) if isinstance(keywords, list) else [],
            "status": getattr(product, "availability", None),
        }
    keywords = product.get("ai_search_keywords") or []
    return {
        "id": product.get("id"),
        "title": product.get("name") or product.get("title"),
        "name": product.get("name") or product.get("title"),
        "original_title": product.get("name") or product.get("original_title") or product.get("title"),
        "description": product.get("description"),
        "ai_search_title": product.get("ai_search_title"),
        "ai_search_description": product.get("ai_search_description"),
        "ai_search_keywords": list(keywords) if isinstance(keywords, list) else [],
        "status": product.get("availability") or product.get("status"),
    }
