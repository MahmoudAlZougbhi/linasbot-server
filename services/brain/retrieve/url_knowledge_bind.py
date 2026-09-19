"""Inbound URL → pin Knowledge identity + scoped retrieve + full hybrid. No auto-send."""

from __future__ import annotations

from typing import Any

from services.ai_setup.knowledge_link_index import (
    extract_raw_urls,
    find_knowledge_by_urls,
    normalize_knowledge_url,
    question_without_urls,
)
from services.brain.contracts.enums import SourceFamily
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.retrieve.cards import TitleCard, load_published_cards
from services.brain.retrieve.orchestrate import retrieve_cards

_PIN_FAMILIES: set[SourceFamily] = {"knowledge", "care"}


def _merge_items(existing: list[EvidenceItem], incoming: list[EvidenceItem]) -> list[EvidenceItem]:
    by_id: dict[str, EvidenceItem] = {}
    order: list[str] = []
    for item in [*existing, *incoming]:
        eid = item.evidence_id or f"{item.source_family}:{item.source_id}"
        if eid in by_id:
            prev = by_id[eid]
            extra = {**(prev.extra or {}), **(item.extra or {})}
            by_id[eid] = prev.model_copy(update={"extra": extra, "text": item.text or prev.text})
            continue
        by_id[eid] = item.model_copy(update={"evidence_id": eid})
        order.append(eid)
    return [by_id[eid] for eid in order if eid in by_id]


def _family(section: str) -> SourceFamily:
    return "care" if section == "care" else "knowledge"


def pin_knowledge_hit(hit: dict[str, Any]) -> EvidenceItem:
    family = _family(str(hit.get("source_section") or "knowledge"))
    item_id = str(hit.get("item_id") or "")
    title = str(hit.get("title") or item_id)
    body = str(hit.get("body") or title)
    return EvidenceItem(
        evidence_id=f"{family}:{item_id}",
        source_family=family,
        source_id=item_id,
        revision=str(hit.get("revision") or ""),
        authority="canonical",
        title=title,
        text=body,
        extra={"url_bind": True, "pin": True, "url_key": hit.get("url_key"), "authority_boost": 200},
    )


def _try_product_pin(*, tenant_id: str, urls: list[str]) -> EvidenceItem | None:
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.brain.retrieve.products import evidence_from_product
        from services.products.repository import ProductsRepository
    except Exception:
        return None
    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return None
            repo = ProductsRepository(session)
            for raw in urls:
                key = normalize_knowledge_url(raw)
                if not key:
                    continue
                row = repo.find_by_link_url(tenant_id=tenant_id, normalized_url=key)
                if row is None:
                    continue
                item = evidence_from_product(row)
                if item is None:
                    continue
                return item.model_copy(update={"extra": {**(item.extra or {}), "url_bind": True, "url_match": True}})
    except WhatsAppDatabaseUnavailable:
        return None
    except Exception:
        return None
    return None


async def scoped_knowledge_retrieve(
    *,
    tenant_id: str,
    query: str,
    hits: list[dict[str, Any]],
) -> tuple[list[EvidenceItem], bool]:
    wanted = {str(hit.get("source_item_id") or "") for hit in hits}
    wanted |= {f"{hit.get('source_section')}:{hit.get('item_id')}" for hit in hits}
    wanted |= {str(hit.get("item_id") or "") for hit in hits}
    cards: list[TitleCard] = [
        card
        for card in load_published_cards(tenant_id)
        if card.source_family in _PIN_FAMILIES and (card.item_id in wanted or card.item_id.split(":", 1)[-1] in wanted)
    ]
    if not cards or not (query or "").strip():
        return [], bool(hits)
    try:
        bundle = await retrieve_cards(cards, query, families=_PIN_FAMILIES, tenant_id=tenant_id)
    except Exception:
        return [], True
    return list(bundle.items), True


async def apply_url_knowledge_bind(
    *,
    tenant_id: str,
    message: str,
    full_bundle: EvidenceBundle,
) -> tuple[EvidenceBundle, dict[str, Any]]:
    meta: dict[str, Any] = {
        "url_bind": False,
        "scoped_retrieve": False,
        "full_retrieve": True,
        "pinned": [],
        "auto_send": False,
        "product_url_match": False,
    }
    urls = extract_raw_urls(message)
    if not urls:
        return full_bundle, meta
    hits = find_knowledge_by_urls(tenant_id=tenant_id, urls=urls)
    pinned = [pin_knowledge_hit(hit) for hit in hits]
    product = _try_product_pin(tenant_id=tenant_id, urls=urls) if not hits else None
    if product is not None:
        pinned.append(product)
        meta["product_url_match"] = True
    if not pinned:
        meta["reason"] = "unknown_url"
        return full_bundle, meta
    query = question_without_urls(message) or str(hits[0].get("title") if hits else pinned[0].title or "")
    scoped_items, scoped_ran = await scoped_knowledge_retrieve(tenant_id=tenant_id, query=query, hits=hits)
    merged = _merge_items(pinned, [*scoped_items, *list(full_bundle.items)])
    meta.update(
        {
            "url_bind": True,
            "scoped_retrieve": scoped_ran,
            "pinned": [item.evidence_id for item in pinned],
            "reason": "knowledge_url_identity",
        }
    )
    outcome = "found" if merged else full_bundle.outcome
    return full_bundle.model_copy(update={"items": merged, "outcome": outcome}), meta
