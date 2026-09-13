"""Attach Luna save-time chunks to title cards. Extra cards only when chunks exist."""

from __future__ import annotations

from typing import Any

from services.customer_ai.compiler.chunk_store import chunk_texts
from services.customer_ai.compiler.prose import POLICY_ITEM_ID, SECTION_ITEM_ID
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.normalize import normalize_search_text
from services.customer_ai.retrieve.cards import TitleCard
from services.search_metadata.fingerprint import item_id_of

_EXTRA_TITLES = {
    ("ai_basics", SECTION_ITEM_ID): ("knowledge", "ai_basics", "AI Basics"),
    ("style", SECTION_ITEM_ID): ("knowledge", "style", "Reply style"),
    ("opening_hours", SECTION_ITEM_ID): ("knowledge", "hours_notes", "Hours notes"),
    ("branches", POLICY_ITEM_ID): ("knowledge", "policy_branches", "Branch notes"),
    ("prices", POLICY_ITEM_ID): ("knowledge", "policy_prices", "Service notes"),
}


def clone_title_card(card: TitleCard, **kwargs: Any) -> TitleCard:
    payload = {
        "item_id": card.item_id,
        "source_family": card.source_family,
        "title": card.title,
        "search_text": card.search_text,
        "revision": card.revision,
        "aliases": card.aliases,
        "body": card.body,
        "chunks": card.chunks,
    }
    payload.update(kwargs)
    return TitleCard(**payload)


def attach_luna_chunks(card: TitleCard, *, tenant_id: str, section: str, item_id: str) -> TitleCard:
    if not tenant_id or not item_id:
        return card
    texts = chunk_texts(tenant_id, section, item_id)
    if not texts:
        return card
    return clone_title_card(card, chunks=texts)


def extra_luna_cards(sections: dict[str, Any], *, revision: str, tenant_id: str) -> list[TitleCard]:
    if not tenant_id:
        return []
    cards: list[TitleCard] = []
    for (section, store_id), (family, source_id, title) in _EXTRA_TITLES.items():
        card = _card_from_store(
            tenant_id=tenant_id,
            section=section,
            store_id=store_id,
            family=family,  # type: ignore[arg-type]
            source_id=source_id,
            title=title,
            revision=revision,
        )
        if card:
            cards.append(card)
    greetings = sections.get("dynamic_messages")
    rows = greetings.get("items") if isinstance(greetings, dict) else None
    if isinstance(rows, list):
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item_id = item_id_of(raw)
            if not item_id:
                continue
            title = str(raw.get("name") or raw.get("title") or item_id).strip() or item_id
            card = _card_from_store(
                tenant_id=tenant_id,
                section="dynamic_messages",
                store_id=item_id,
                family="knowledge",
                source_id=f"dm_{item_id}",
                title=title,
                revision=revision,
            )
            if card:
                cards.append(card)
    requests = sections.get("requests_appointments")
    rules = requests.get("rules") if isinstance(requests, dict) else None
    if isinstance(rules, list):
        for raw in rules:
            if not isinstance(raw, dict):
                continue
            item_id = item_id_of(raw)
            if not item_id:
                continue
            title = str(raw.get("name") or item_id).strip() or item_id
            card = _card_from_store(
                tenant_id=tenant_id,
                section="requests_appointments",
                store_id=item_id,
                family="requests",
                source_id=item_id,
                title=title,
                revision=revision,
            )
            if card:
                cards.append(card)
    return cards


def _card_from_store(
    *,
    tenant_id: str,
    section: str,
    store_id: str,
    family: SourceFamily,
    source_id: str,
    title: str,
    revision: str,
) -> TitleCard | None:
    texts = chunk_texts(tenant_id, section, store_id)
    if not texts:
        return None
    body = "\n\n".join(texts)
    search = normalize_search_text(body)
    if not search:
        return None
    return TitleCard(
        item_id=f"{family}:{source_id}",
        source_family=family,
        title=title,
        search_text=search,
        revision=revision,
        body=body,
        chunks=texts,
    )
