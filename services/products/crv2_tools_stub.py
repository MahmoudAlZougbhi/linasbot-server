"""CRV2 product tool stubs — Phase 2 wires these into retrieval_tools."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.products.search import search_product_by_title


def crv2_search_product_by_title(
    session: Session,
    *,
    tenant_id: str,
    title: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Minimal deterministic tool response for Customer Reply V2 (Phase 1 stub)."""
    matches = search_product_by_title(
        session,
        tenant_id=tenant_id,
        title=title,
        limit=limit,
    )
    return {
        "tool": "search_product_by_title",
        "query": title,
        "match_count": len(matches),
        "matches": matches,
    }
