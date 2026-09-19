"""Bounded product TitleCards for retrieve/tools. Never dumps the full catalog."""

from __future__ import annotations

from services.brain.retrieve.cards import TitleCard
from services.brain.retrieve.products import cards_from_products

QUERY_CAP = 24


def search_product_cards(tenant_id: str, query: str, *, limit: int = QUERY_CAP) -> list[TitleCard]:
    """SQL contains search → cards for the hit ids only (customer-facing)."""
    tid = (tenant_id or "").strip()
    needle = (query or "").strip()
    cap = min(max(int(limit or QUERY_CAP), 1), QUERY_CAP)
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
