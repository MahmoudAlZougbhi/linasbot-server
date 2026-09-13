"""Published catalog prices with branch labels. Never invent an amount or branch."""

from __future__ import annotations

from typing import Any


def branch_names(sections: dict[str, Any], branch_id: str | None) -> str:
    bid = str(branch_id or "").strip()
    if not bid:
        return "all branches"
    payload = sections.get("branches")
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return bid
    for raw in items:
        if not isinstance(raw, dict) or str(raw.get("id") or "").strip() != bid:
            continue
        names = [bid]
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if title:
            names.append(title)
        labels = raw.get("labels")
        if isinstance(labels, dict):
            for key in ("en", "ar", "fr", "franco"):
                value = str(labels.get(key) or "").strip()
                if value and value not in names:
                    names.append(value)
        aliases = raw.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                text = str(alias or "").strip()
                if text and text not in names:
                    names.append(text)
        return " ".join(names)
    return bid


def price_evidence_lines(sections: dict[str, Any], catalog_item_id: str) -> list[str]:
    cid = str(catalog_item_id or "").strip()
    if not cid:
        return []
    raw = sections.get("prices")
    if not isinstance(raw, dict):
        return []
    try:
        from services.cm.pricing.section import normalize_prices_section, section_price_entries

        section = normalize_prices_section(raw)
        entries = section_price_entries(section)
    except Exception:
        return []
    lines: list[str] = []
    for entry in entries:
        if entry.catalog_item_id != cid or not entry.active:
            continue
        unit = f" / {entry.unit}" if entry.unit else ""
        names = branch_names(sections, entry.branch_id)
        lines.append(f"branch {names}: {entry.amount} {entry.currency}{unit}".strip())
    return lines


def price_search_blob(sections: dict[str, Any], catalog_item_id: str) -> str:
    return " ".join(price_evidence_lines(sections, catalog_item_id))
