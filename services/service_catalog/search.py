"""Deterministic service name search for customer AI pricing lookups."""

from __future__ import annotations

import difflib
from typing import Any

from sqlalchemy.orm import Session

from services.service_catalog.repository import ServiceCatalogRepository
from services.service_catalog.schemas import normalize_service_name, service_to_dict

MIN_SCORE = 0.55


def search_service_by_name(
    session: Session,
    *,
    tenant_id: str,
    name: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query = normalize_service_name(name)
    if not query:
        return []

    repo = ServiceCatalogRepository(session)
    prefix_hits = repo.search_by_name_prefix(tenant_id=tenant_id, query=query, limit=limit)
    if prefix_hits:
        return [service_to_dict(row) for row in prefix_hits[:limit]]

    candidates = repo.list_all_for_tenant(tenant_id=tenant_id)
    scored: list[tuple[float, Any]] = []
    for row in candidates:
        ratio = difflib.SequenceMatcher(None, query, row.name_normalized).ratio()
        if ratio >= MIN_SCORE:
            scored.append((ratio, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [service_to_dict(row) for _, row in scored[:limit]]
