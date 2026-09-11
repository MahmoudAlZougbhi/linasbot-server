"""Publish-time title cards. Search these, then hydrate winners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.normalize import normalize_search_text


@dataclass(frozen=True)
class TitleCard:
    item_id: str
    source_family: SourceFamily
    title: str
    search_text: str
    revision: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    body: str = ""


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
        if family in {"knowledge", "care"} and tenant_id:
            attachments = raw.get("attachments") or []
            if attachments:
                from services.cm.article_media import format_attachments_block

                block = format_attachments_block(list(attachments), tenant_id=tenant_id)
                if block:
                    body = f"{body}\n\n{block}".strip() if body else block
        extra = [
            str(raw.get("ai_search_title") or ""),
            str(raw.get("ai_search_description") or ""),
            str(raw.get("description") or ""),
            " ".join(str(a) for a in (raw.get("aliases") or [])),
            " ".join(str(t) for t in (raw.get("tags") or [])),
        ]
        if family == "faq":
            for variant in raw.get("variants") or []:
                if isinstance(variant, dict):
                    extra.append(str(variant.get("question") or ""))
        if family in {"knowledge", "care"} and body:
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
    if not any(card.source_family == "hours" for card in cards):
        branches = sections.get("branches")
        items = branches.get("items") if isinstance(branches, dict) else None
        if isinstance(items, list):
            cards.extend(_from_items("hours", items, revision, tenant_id=tenant_id))
    # Mobile Services screen writes published CM prices.catalog — that is the service SoT.
    prices = sections.get("prices")
    catalog = prices.get("catalog") if isinstance(prices, dict) else None
    if isinstance(catalog, list) and catalog:
        cards.extend(_from_items("services", catalog, revision, tenant_id=tenant_id))
    else:
        legacy = sections.get("services")
        rows = legacy.get("items") if isinstance(legacy, dict) else None
        if isinstance(rows, list):
            cards.extend(_from_items("services", rows, revision, tenant_id=tenant_id))
    return cards


def load_published_cards(tenant_id: str) -> list[TitleCard]:
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return []
    revision = str(getattr(pointer, "revision", "") or getattr(pointer, "etag", "") or "")
    return cards_from_sections(sections, revision=revision, tenant_id=tenant_id)
