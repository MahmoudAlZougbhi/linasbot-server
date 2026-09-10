"""Products adapter. Postgres `products.updated_at` is the revision stand-in."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.evidence import EvidenceItem
from services.customer_ai.retrieve.cards import TitleCard, _card
from services.products.availability import is_customer_searchable


def _attr(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def product_revision(row: Any) -> str:
    raw = _attr(row, "updated_at", "")
    if hasattr(raw, "isoformat"):
        return str(raw.isoformat())
    return str(raw or "")


def cards_from_products(rows: list[Any]) -> list[TitleCard]:
    cards: list[TitleCard] = []
    for row in rows:
        if not is_customer_searchable(str(_attr(row, "availability") or "")):
            continue
        item_id = str(_attr(row, "id") or "").strip()
        title = str(_attr(row, "name") or _attr(row, "ai_search_title") or "").strip()
        keywords = _attr(row, "ai_search_keywords") or []
        extra = [
            str(_attr(row, "ai_search_title") or ""),
            str(_attr(row, "ai_search_description") or ""),
            str(_attr(row, "description") or ""),
            " ".join(str(k) for k in keywords) if isinstance(keywords, list) else str(keywords),
        ]
        card = _card(
            family="products",
            item_id=item_id,
            title=title,
            extra=extra,
            revision=product_revision(row),
        )
        if card:
            cards.append(card)
    return cards


def evidence_from_product(row: Any) -> EvidenceItem | None:
    item_id = str(_attr(row, "id") or "").strip()
    if not item_id or not is_customer_searchable(str(_attr(row, "availability") or "")):
        return None
    title = str(_attr(row, "name") or "").strip()
    parts = [
        title,
        str(_attr(row, "description") or ""),
        str(_attr(row, "note") or ""),
    ]
    price = _attr(row, "price")
    if price:
        parts.append(f"listed_price {price}")
    parts.append(f"availability { _attr(row, 'availability') }")
    text = "\n".join(p.strip() for p in parts if str(p).strip())
    if not text:
        return None
    return EvidenceItem(
        evidence_id=f"products:{item_id}",
        source_family="products",
        source_id=item_id,
        revision=product_revision(row),
        title=title or item_id,
        text=text,
        extra={"availability": str(_attr(row, "availability") or ""), "listed_price": str(price or "")},
    )


def load_product_cards(tenant_id: str) -> list[TitleCard]:
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.products.repository import ProductsRepository
    except Exception:
        return []
    try:
        with whatsapp_session(require=True) as session:
            rows = ProductsRepository(session).list_all_for_tenant(tenant_id=tid, customer_facing=True)
            return cards_from_products(rows)
    except WhatsAppDatabaseUnavailable:
        return []
    except Exception:
        return []
