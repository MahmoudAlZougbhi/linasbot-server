"""Hydrate canonical text for winning IDs only. No media bytes."""

from __future__ import annotations

from typing import Any

from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.retrieve.lexical import LexicalHit


def _rows(sections: dict[str, Any], family: str) -> list[dict[str, Any]]:
    if family == "hours":
        payload = sections.get("opening_hours")
        rows = payload.get("items") if isinstance(payload, dict) else None
        return [r for r in rows or [] if isinstance(r, dict)]
    if family in {"prices", "services"}:
        payload = sections.get("prices")
        catalog = payload.get("catalog") if isinstance(payload, dict) else None
        if isinstance(catalog, list) and catalog:
            return [r for r in catalog if isinstance(r, dict)]
        if family == "services":
            legacy = sections.get("services")
            rows = legacy.get("items") if isinstance(legacy, dict) else None
            return [r for r in rows or [] if isinstance(r, dict)]
        return []
    payload = sections.get(family)
    rows = payload.get("items") if isinstance(payload, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def _row_id(raw: dict[str, Any]) -> str:
    return str(raw.get("id") or raw.get("qa_group_id") or "").strip()


def _label(labels: Any) -> str:
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
    return ""


def _price_lines(sections: dict[str, Any], catalog_item_id: str) -> list[str]:
    from services.cm.pricing.section import normalize_prices_section, section_price_entries

    raw = sections.get("prices")
    if not isinstance(raw, dict):
        return []
    section = normalize_prices_section(raw)
    lines: list[str] = []
    for entry in section_price_entries(section):
        if entry.catalog_item_id != catalog_item_id or not entry.active:
            continue
        unit = f" / {entry.unit}" if entry.unit else ""
        lines.append(f"{entry.amount} {entry.currency}{unit}".strip())
    return lines


def _text_card(family: str, raw: dict[str, Any], *, sections: dict[str, Any]) -> str:
    parts = [
        str(raw.get("title") or raw.get("name") or _label(raw.get("labels")) or ""),
        str(raw.get("description") or raw.get("body") or raw.get("notes") or ""),
        str(raw.get("ai_search_description") or ""),
    ]
    if family in {"services", "prices"}:
        if raw.get("base_price") is not None:
            parts.append(f"{raw.get('base_price')} {raw.get('currency') or ''}".strip())
        parts.extend(_price_lines(sections, str(raw.get("id") or "")))
    if family == "faq":
        for variant in raw.get("variants") or []:
            if isinstance(variant, dict):
                parts.append(str(variant.get("answer") or ""))
    if family == "branches":
        parts.append(str(raw.get("address") or raw.get("maps_url") or ""))
    if family == "hours":
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            row = raw.get(day)
            if not isinstance(row, dict):
                continue
            if row.get("closed"):
                parts.append(f"{day}: closed")
            elif row.get("open") or row.get("close"):
                parts.append(f"{day}: {row.get('open') or ''}–{row.get('close') or ''}".strip())
    return "\n".join(p.strip() for p in parts if str(p).strip())


def expand_ranked(
    ranked: list[Any],
    sections: dict[str, Any],
    *,
    revision: str = "",
) -> EvidenceBundle:
    hits: list[LexicalHit] = []
    for item in ranked:
        card = getattr(item, "card", None)
        if card is None:
            continue
        score = float(getattr(item, "lexical_score", 0.0) or getattr(item, "score", 0.0) or 0.0)
        hits.append(LexicalHit(card=card, score=score))
    return expand_hits(hits, sections, revision=revision)


def expand_hits(
    hits: list[LexicalHit],
    sections: dict[str, Any],
    *,
    revision: str = "",
) -> EvidenceBundle:
    items: list[EvidenceItem] = []
    for hit in hits:
        card = hit.card
        _, _, source_id = card.item_id.partition(":")
        family = card.source_family
        match = next((row for row in _rows(sections, family) if _row_id(row) == source_id), None)
        if match is None:
            continue
        text = _text_card(family, match, sections=sections)
        if not text:
            continue
        items.append(
            EvidenceItem(
                evidence_id=card.item_id,
                source_family=family,
                source_id=source_id,
                revision=revision or card.revision,
                title=card.title,
                text=text,
                extra={"lexical_score": hit.score},
            )
        )
    outcome = "found" if items else "not_found"
    return EvidenceBundle(items=items, outcome=outcome)  # type: ignore[arg-type]


def expand_published(tenant_id: str, hits: list[LexicalHit]) -> EvidenceBundle:
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return EvidenceBundle(outcome="source_unpublished")
    revision = str(getattr(pointer, "revision", "") or "")
    return expand_hits(hits, sections, revision=revision)
