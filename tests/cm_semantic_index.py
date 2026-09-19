"""Test-only FAQ/knowledge/catalog entry extractors.

Live publish indexes with Voyage (Brain). Do not call this module from publish.
"""

from __future__ import annotations

from typing import Any

from services.ai_setup.schemas import CareSection, FaqSection, KnowledgeSection

_RawEntry = tuple[str, str, str, str, dict[str, Any]]  # source_id, kind, language, text, metadata


def _faq_entries(payload: dict[str, Any] | None) -> list[_RawEntry]:
    out: list[_RawEntry] = []
    if not payload:
        return out
    section = FaqSection.model_validate(payload)
    for item in section.items:
        if item.status in {"archived", "restricted"}:
            continue
        for variant in item.variants:
            if not variant.question:
                continue
            source_id = f"faq:{item.qa_group_id}:{variant.language}"
            out.append(
                (
                    source_id,
                    "faq",
                    variant.language,
                    variant.question,
                    {"qa_group_id": item.qa_group_id, "answer": variant.answer, "tags": list(item.tags)},
                )
            )
    return out


def _article_entries(
    payload: dict[str, Any] | None,
    kind: str,
    *,
    tenant_id: str | None = None,
) -> list[_RawEntry]:
    from services.ai_setup.article_media import format_attachments_block

    out: list[_RawEntry] = []
    if not payload:
        return out
    model_cls: type[KnowledgeSection] | type[CareSection] = KnowledgeSection if kind == "knowledge" else CareSection
    section = model_cls.model_validate(payload)
    for item in section.items:
        if item.status in {"archived", "restricted"}:
            continue
        parts = [f"{item.title}\n{item.body}".strip()]
        att_block = format_attachments_block(list(item.attachments), tenant_id=tenant_id)
        if att_block:
            parts.append(att_block)
        text = "\n\n".join(p for p in parts if p).strip()
        if not text:
            continue
        source_id = f"{kind}:{item.id}"
        out.append(
            (
                source_id,
                kind,
                item.language or "",
                text,
                {
                    "title": item.title,
                    "tags": list(item.tags),
                    "attachment_count": len(item.attachments),
                },
            )
        )
    return out


def _price_catalog_entries(
    payload: dict[str, Any] | None,
    *,
    tenant_id: str | None = None,
) -> list[_RawEntry]:
    """Index service catalog names, notes, prices, and shared media captions."""
    from services.ai_setup.article_media import format_attachments_block
    from services.ai_setup.pricing.section import normalize_prices_section, section_catalog_items, section_price_entries

    out: list[_RawEntry] = []
    if not payload:
        return out
    section = normalize_prices_section(payload)
    entries = section_price_entries(section)
    for item in section_catalog_items(section):
        if not item.active:
            continue
        labels = item.labels.model_dump()
        name = ""
        for key in ("en", "ar", "fr", "franco"):
            text = str(labels.get(key) or "").strip()
            if text:
                name = text
                break
        name = name or item.id
        note = (item.description or item.notes or "").strip()
        price_bits: list[str] = []
        for entry in entries:
            if entry.catalog_item_id != item.id or not entry.active:
                continue
            title = (entry.notes or "").strip() or "price"
            price_bits.append(f"{title}: {entry.amount} {entry.currency}")
        parts = [name]
        if note:
            parts.append(note)
        if price_bits:
            parts.append("Prices: " + "; ".join(price_bits))
        att_block = format_attachments_block(list(item.attachments), tenant_id=tenant_id)
        if att_block:
            parts.append(att_block)
        text = "\n".join(parts).strip()
        if not text:
            continue
        out.append(
            (
                f"prices:{item.id}",
                "prices",
                "",
                text,
                {"title": name, "attachment_count": len(item.attachments)},
            )
        )
    return out
