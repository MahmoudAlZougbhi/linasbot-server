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
        hours = [r for r in rows or [] if isinstance(r, dict)]
        if hours:
            return hours
        branches = sections.get("branches")
        items = branches.get("items") if isinstance(branches, dict) else None
        return [r for r in items or [] if isinstance(r, dict)]
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


def _schedule_lines(raw: dict[str, Any]) -> list[str]:
    nested = raw.get("weekly_hours") or raw.get("hours") or raw.get("schedule")
    schedule = nested if isinstance(nested, dict) else raw
    lines: list[str] = []
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        row = schedule.get(day)
        if not isinstance(row, dict):
            continue
        if row.get("closed"):
            lines.append(f"{day}: closed")
        elif row.get("open") or row.get("close"):
            lines.append(f"{day}: {row.get('open') or ''}–{row.get('close') or ''}".strip())
    exceptions = raw.get("exceptions") or raw.get("off_days") or []
    if isinstance(exceptions, list):
        for item in exceptions:
            lines.append(str(item))
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
        tz = str(raw.get("timezone") or raw.get("tz") or "").strip()
        if tz:
            parts.append(f"timezone {tz}")
        parts.extend(_schedule_lines(raw))
    if family == "hours":
        tz = str(raw.get("timezone") or raw.get("tz") or "").strip()
        if tz:
            parts.append(f"timezone {tz}")
        parts.extend(_schedule_lines(raw))
    return "\n".join(p.strip() for p in parts if str(p).strip())


def expand_ranked(
    ranked: list[Any],
    sections: dict[str, Any],
    *,
    revision: str = "",
    tenant_id: str = "",
) -> EvidenceBundle:
    hits: list[LexicalHit] = []
    for item in ranked:
        card = getattr(item, "card", None)
        if card is None:
            continue
        score = float(getattr(item, "lexical_score", 0.0) or getattr(item, "score", 0.0) or 0.0)
        hits.append(LexicalHit(card=card, score=score))
    return expand_hits(hits, sections, revision=revision, tenant_id=tenant_id)


def expand_hits(
    hits: list[LexicalHit],
    sections: dict[str, Any],
    *,
    revision: str = "",
    tenant_id: str = "",
) -> EvidenceBundle:
    items: list[EvidenceItem] = []
    for hit in hits:
        card = hit.card
        _, _, source_id = card.item_id.partition(":")
        family = card.source_family
        if family == "products":
            from services.customer_ai.retrieve.products import evidence_from_product, load_product_evidence

            match = next((row for row in _rows(sections, family) if _row_id(row) == source_id), None)
            if match is not None:
                product_item = evidence_from_product(match)
            else:
                product_item = load_product_evidence(tenant_id, source_id)
            if product_item is None:
                continue
            items.append(
                product_item.model_copy(
                    update={
                        "revision": revision or product_item.revision or card.revision,
                        "extra": {**(product_item.extra or {}), "lexical_score": hit.score},
                    }
                )
            )
            continue
        match = next((row for row in _rows(sections, family) if _row_id(row) == source_id), None)
        if match is None:
            continue
        if family == "knowledge" and (card.body or "").strip():
            chunk = card.body.strip()
            full = _text_card(family, match, sections=sections)
            # Prefer indexed winning chunk when shorter than (or equal to) the full article.
            text = chunk if (not full or len(chunk) <= len(full)) else full
        else:
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
    return expand_hits(hits, sections, revision=revision, tenant_id=tenant_id)
