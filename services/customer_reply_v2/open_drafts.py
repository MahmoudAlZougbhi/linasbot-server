"""Open customer request drafts. Phase 7 fills storage; Phase 2 only exposes the guard."""

from __future__ import annotations

from typing import Any


def list_open_collecting_drafts(
    *,
    tenant_id: str,
    customer_id: str = "",
) -> list[dict[str, Any]]:
    """Return open collecting drafts for this tenant+customer. Empty until draft engine exists."""
    _ = (tenant_id, customer_id)
    return []


def has_open_collecting_draft(*, tenant_id: str, customer_id: str = "") -> bool:
    return bool(list_open_collecting_drafts(tenant_id=tenant_id, customer_id=customer_id))
