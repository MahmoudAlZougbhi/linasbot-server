"""CRV2 service pricing tool stub — mirrors products search pattern."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.service_catalog.search import search_service_by_name


def crv2_search_service_by_name(
    session: Session,
    *,
    tenant_id: str,
    name: str,
    limit: int = 5,
) -> dict[str, Any]:
    matches = search_service_by_name(
        session,
        tenant_id=tenant_id,
        name=name,
        limit=limit,
    )
    return {
        "tool": "search_service_by_name",
        "query": name,
        "match_count": len(matches),
        "matches": matches,
    }
