"""Product index freshness for Brain product questions."""

from __future__ import annotations

from typing import Any


def products_index_stale(tenant_id: str) -> bool:
    tid = (tenant_id or "").strip()
    if not tid:
        return False
    try:
        from services.customer_ai.search.store import get_source_pointer_ready

        pointer = get_source_pointer_ready(tid, "products")
    except Exception:
        return False
    if pointer is None:
        return False
    if pointer.get("ready") is False:
        return True
    return False


def product_questions_blocked(tenant_id: str, families: set[str] | None) -> dict[str, Any] | None:
    if families is not None and "products" not in families:
        return None
    if not products_index_stale(tenant_id):
        return None
    return {
        "ok": False,
        "reason": "product_index_stale",
        "message": "Product catalog changed; reindex before Brain can answer product questions.",
    }
