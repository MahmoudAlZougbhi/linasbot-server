"""Hydrate product evidence by id after a vector/lexical hit list. No catalog dump."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.evidence import EvidenceItem
from services.brain.retrieve.lexical import LexicalHit
from services.brain.retrieve.products import evidence_from_product

BATCH_CAP = 32


def load_product_evidence_map(tenant_id: str, product_ids: list[str]) -> dict[str, EvidenceItem]:
    """Batch-get products for the winning ids only."""
    tid = (tenant_id or "").strip()
    ids = [str(item or "").strip() for item in product_ids if str(item or "").strip()]
    ids = list(dict.fromkeys(ids))[:BATCH_CAP]
    if not tid or not ids:
        return {}
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.products.repository import ProductsRepository
    except Exception:
        return {}
    try:
        with whatsapp_session(require=True) as session:
            rows = ProductsRepository(session).get_products_by_ids(tenant_id=tid, product_ids=ids)
    except WhatsAppDatabaseUnavailable:
        return {}
    except Exception:
        return {}
    out: dict[str, EvidenceItem] = {}
    for row in rows:
        item = evidence_from_product(row)
        if item is not None:
            out[item.source_id] = item
    return out


def expand_product_hits(
    hits: list[LexicalHit],
    *,
    tenant_id: str,
    revision: str = "",
) -> list[EvidenceItem]:
    ids = [_source_id(hit.card.item_id) for hit in hits]
    by_id = load_product_evidence_map(tenant_id, ids)
    items: list[EvidenceItem] = []
    for hit in hits:
        source_id = _source_id(hit.card.item_id)
        product_item = by_id.get(source_id)
        if product_item is None:
            continue
        extra = {**(product_item.extra or {}), "lexical_score": hit.score}
        items.append(
            product_item.model_copy(
                update={"revision": revision or product_item.revision or hit.card.revision, "extra": extra}
            )
        )
    return items


def evidence_for_product_ids(
    tenant_id: str,
    product_ids: list[str],
    *,
    extra: dict[str, Any] | None = None,
) -> list[EvidenceItem]:
    by_id = load_product_evidence_map(tenant_id, product_ids)
    marker = extra or {}
    items: list[EvidenceItem] = []
    for pid in product_ids:
        item = by_id.get(str(pid or "").strip())
        if item is None:
            continue
        items.append(item.model_copy(update={"extra": {**(item.extra or {}), **marker}}))
    return items


def _source_id(item_id: str) -> str:
    _, _, source_id = (item_id or "").partition(":")
    return source_id or item_id
