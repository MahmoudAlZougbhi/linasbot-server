"""Product/source changes must stale the Customer Brain index without a CM republish."""

from __future__ import annotations

from typing import Any

from services.customer_ai.search.store import mark_pointer_not_ready


def mark_products_stale(session: Any | None, tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ok": False, "reason": "missing_tenant"}
    mark_pointer_not_ready(session, tenant_id=tid, source_family="products", reason="source_changed")
    if session is None:
        return {"ok": True, "reason": "source_changed", "backend": "memory"}
    try:
        from sqlalchemy import text

        session.execute(
            text(
                """
                UPDATE customer_ai_search_documents
                SET visible = false, updated_at = now()
                WHERE tenant_id = :tenant_id AND source_family = 'products'
                """
            ),
            {"tenant_id": tid},
        )
        return {"ok": True, "reason": "source_changed", "backend": "pgvector"}
    except Exception:
        return {"ok": True, "reason": "source_changed", "backend": "best_effort"}


def notify_product_change(session: Any | None, tenant_id: str) -> None:
    try:
        mark_products_stale(session, tenant_id)
    except Exception:
        return
