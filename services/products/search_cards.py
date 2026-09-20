"""Bounded product TitleCards for retrieve/tools. Never dumps the full catalog."""

from __future__ import annotations

from services.brain.retrieve.cards import TitleCard
from services.brain.retrieve.products import cards_from_products

QUERY_CAP = 24


def search_product_cards(tenant_id: str, query: str, *, limit: int | None = None) -> list[TitleCard]:
    """SQL contains search → cards for the hit ids only (customer-facing)."""
    tid = (tenant_id or "").strip()
    needle = (query or "").strip()
    default_cap = QUERY_CAP
    if tid:
        from services.runtime_limits.loader import load_runtime_limits

        default_cap = load_runtime_limits(tid).product_search_cap
    cap = min(max(int(limit if limit is not None else default_cap), 1), 200)
    if not tid or not needle:
        return []
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.products.repository import ProductsRepository
    except Exception:
        return []
    try:
        with whatsapp_session(require=True) as session:
            rows = ProductsRepository(session).search_by_title_prefix(
                tenant_id=tid,
                query=needle,
                limit=cap,
                customer_facing=True,
            )
            return cards_from_products(rows)
    except WhatsAppDatabaseUnavailable:
        return []
    except Exception:
        return []
