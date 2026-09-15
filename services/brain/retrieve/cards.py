"""Publish-time title cards. Search these, then hydrate winners."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from services.ai_setup.version_store import PublishedVersionError, load_published_content
from services.brain.contracts.enums import SourceFamily
from services.brain.normalize import normalize_search_text


@dataclass(frozen=True)
class TitleCard:
    item_id: str
    source_family: SourceFamily
    title: str
    search_text: str
    revision: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    body: str = ""
    chunks: tuple[str, ...] = field(default_factory=tuple)


def _label(labels: Any) -> str:
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
    return ""


def _card(
    *,
    family: SourceFamily,
    item_id: str,
    title: str,
    extra: list[str],
    revision: str = "",
    body: str = "",
) -> TitleCard | None:
    if not item_id:
        return None
    parts = [title, *extra]
    search = normalize_search_text(" ".join(p for p in parts if p))
    if not search:
        return None
    return TitleCard(
        item_id=f"{family}:{item_id}",
        source_family=family,
        title=title or item_id,
        search_text=search,
        revision=revision,
        aliases=tuple(p for p in extra if p),
        body=body.strip(),
    )


def _from_items(
    family: SourceFamily,
    rows: list[Any],
    revision: str,
    *,
    tenant_id: str = "",
) -> list[TitleCard]:
    cards: list[TitleCard] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "active").strip().lower()
        if status in {"archived", "draft", "deleted", "inactive", "withdrawn"}:
            continue
        if raw.get("active") is False:
            continue
        item_id = str(raw.get("id") or raw.get("qa_group_id") or "").strip()
        title = str(raw.get("title") or raw.get("name") or _label(raw.get("labels")) or "").strip()
        body = str(raw.get("body") or raw.get("content") or raw.get("text") or raw.get("description") or "")
        if family in {"knowledge", "care", "branches", "hours", "services"} and tenant_id:
            attachments = raw.get("attachments") or []
            if attachments:
                from services.ai_setup.article_media import format_attachments_block

                block = format_attachments_block(list(attachments), tenant_id=tenant_id)
                if block:
                    body = f"{body}\n\n{block}".strip() if body else block
        label_langs: list[str] = []
        labels = raw.get("labels")
        if isinstance(labels, dict):
            for key in ("en", "ar", "fr", "franco"):
                value = str(labels.get(key) or "").strip()
                if value:
                    label_langs.append(value)
        extra = [
            str(raw.get("ai_search_title") or ""),
            str(raw.get("ai_search_description") or ""),
            str(raw.get("description") or ""),
            " ".join(str(a) for a in (raw.get("aliases") or [])),
            " ".join(str(t) for t in (raw.get("tags") or [])),
            " ".join(label_langs),
        ]
        if family in {"hours", "branches"}:
            from services.brain.retrieve.schedule_text import schedule_search_blob

            extra.append(schedule_search_blob(raw))
        if family == "faq":
            for variant in raw.get("variants") or []:
                if isinstance(variant, dict):
                    extra.append(str(variant.get("question") or ""))
        if family in {"knowledge", "care", "branches", "hours", "services"} and body:
            extra.append(body)
        card = _card(family=family, item_id=item_id, title=title, extra=extra, revision=revision, body=body)
        if card:
            cards.append(card)
    return cards


def cards_from_sections(
    sections: dict[str, Any],
    *,
    revision: str = "",
    tenant_id: str = "",
) -> list[TitleCard]:
    cards: list[TitleCard] = []
    mapping: list[tuple[str, SourceFamily]] = [
        ("knowledge", "knowledge"),
        ("care", "care"),
        ("branches", "branches"),
        ("faq", "faq"),
        ("opening_hours", "hours"),
    ]
    for key, family in mapping:
        payload = sections.get(key)
        if not isinstance(payload, dict):
            continue
        rows = payload.get("items")
        if isinstance(rows, list):
            cards.extend(_from_items(family, rows, revision, tenant_id=tenant_id))
    # Always index branch weekly_schedule as hours cards. Opening-hours rows
    # must not hide published branch clocks when both sections exist.
    branches = sections.get("branches")
    items = branches.get("items") if isinstance(branches, dict) else None
    if isinstance(items, list):
        existing = {card.item_id: index for index, card in enumerate(cards) if card.source_family == "hours"}
        for card in _from_items("hours", items, revision, tenant_id=tenant_id):
            prior = existing.get(card.item_id)
            if prior is None:
                existing[card.item_id] = len(cards)
                cards.append(card)
                continue
            old = cards[prior]
            if card.search_text and card.search_text not in old.search_text:
                cards[prior] = TitleCard(
                    item_id=old.item_id,
                    source_family=old.source_family,
                    title=old.title,
                    search_text=normalize_search_text(f"{old.search_text} {card.search_text}"),
                    revision=old.revision or card.revision,
                    aliases=tuple(dict.fromkeys([*old.aliases, *card.aliases])),
                    body=old.body or card.body,
                    chunks=old.chunks or card.chunks,
                )
    # Mobile Services screen writes published CM prices.catalog — that is the service SoT.
    prices = sections.get("prices")
    catalog = prices.get("catalog") if isinstance(prices, dict) else None
    if isinstance(catalog, list) and catalog:
        from services.brain.retrieve.price_text import price_search_blob

        for service_card in _from_items("services", catalog, revision, tenant_id=tenant_id):
            source_id = service_card.item_id.partition(":")[2]
            blob = price_search_blob(sections, source_id)
            if blob:
                service_card = replace(
                    service_card,
                    search_text=normalize_search_text(f"{service_card.search_text} {blob}"),
                )
            cards.append(service_card)
    off_payload = sections.get("off_days")
    if isinstance(off_payload, dict):
        from services.brain.retrieve.schedule_text import off_days_search_blob

        blob = off_days_search_blob(off_payload)
        if blob:
            off_card = _card(
                family="hours",
                item_id="off_days",
                title="Off days",
                extra=[blob],
                revision=revision,
                body=blob,
            )
            if off_card is not None:
                cards.append(off_card)
    return _attach_saved_chunks(cards, tenant_id)


_SECTION_FOR_FAMILY = {
    "knowledge": "knowledge",
    "care": "care",
    "branches": "branches",
    "services": "prices",
}


def _attach_saved_chunks(cards: list[TitleCard], tenant_id: str) -> list[TitleCard]:
    """Hydrate save-time sidecar texts for Voyage. Disk read only — no chunker LLM."""
    if not tenant_id:
        return cards
    from services.brain.compiler.chunk_store import chunk_texts

    attached: list[TitleCard] = []
    for card in cards:
        section = _SECTION_FOR_FAMILY.get(card.source_family)
        if not section:
            attached.append(card)
            continue
        source_id = card.item_id.partition(":")[2]
        texts = chunk_texts(tenant_id, section, source_id)
        if texts:
            attached.append(replace(card, chunks=texts))
        else:
            attached.append(card)
    return attached


def load_published_cards(tenant_id: str) -> list[TitleCard]:
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return []
    revision = str(getattr(pointer, "revision", "") or getattr(pointer, "etag", "") or "")
    return cards_from_sections(sections, revision=revision, tenant_id=tenant_id)
