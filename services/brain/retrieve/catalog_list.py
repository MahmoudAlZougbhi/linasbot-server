"""Bounded catalog dump for list/catalog questions (active published entities only)."""

from __future__ import annotations

from services.brain.catalog_intent import catalog_filter_tokens
from services.brain.contracts.enums import SourceFamily
from services.brain.contracts.evidence import EvidenceItem
from services.brain.normalize import normalize_search_text
from services.brain.retrieve.cards import TitleCard, load_published_cards
from services.brain.retrieve.products import load_product_cards

CATALOG_CAP = 18
_LIST_FAMILIES = {"services", "products", "prices"}


def _wanted_families(families: set[SourceFamily] | None) -> set[str]:
    if not families:
        return set(_LIST_FAMILIES)
    cleaned = {str(item) for item in families if str(item) in _LIST_FAMILIES or str(item) == "services"}
    return cleaned or set(_LIST_FAMILIES)


def _passes_filter(card: TitleCard, filters: list[str]) -> bool:
    if not filters:
        return True
    blob = normalize_search_text(f"{card.title} {card.search_text} {' '.join(card.aliases)}")
    return any(token in blob for token in filters)


def catalog_list_items(
    tenant_id: str,
    query: str,
    *,
    families: set[SourceFamily] | None = None,
    revision: str = "",
    limit: int = CATALOG_CAP,
) -> list[EvidenceItem]:
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    wanted = _wanted_families(families)
    cards = [card for card in load_published_cards(tid) + load_product_cards(tid) if card.source_family in wanted]
    filters = catalog_filter_tokens(query)
    matched = [card for card in cards if _passes_filter(card, filters)] or list(cards)
    matched.sort(key=lambda card: (card.source_family, card.title.casefold(), card.item_id))
    items: list[EvidenceItem] = []
    for card in matched[: max(1, limit)]:
        _, _, source_id = card.item_id.partition(":")
        text = (card.body or card.search_text or card.title).strip()
        if not text:
            continue
        items.append(
            EvidenceItem(
                evidence_id=card.item_id,
                source_family=card.source_family,
                source_id=source_id or card.item_id,
                revision=revision or card.revision,
                title=card.title,
                text=text[:800],
                extra={
                    "catalog_list": True,
                    "entity_id": source_id or card.item_id,
                    "entity_type": card.source_family,
                    "tenant_id": tid,
                    "bundle": "+" in card.title or " and " in card.title.casefold(),
                },
            )
        )
    return items
