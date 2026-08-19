"""Retrieval view: original user title + AI search title + short AI description."""

from __future__ import annotations

from typing import Any


def _label_of(labels: Any) -> str:
    if isinstance(labels, dict):
        return str(labels.get("en") or labels.get("ar") or labels.get("fr") or "").strip()
    return str(getattr(labels, "en", "") or getattr(labels, "ar", "") or "").strip()


def original_title_of(raw: dict[str, Any]) -> str:
    title = str(raw.get("title") or raw.get("name") or "").strip()
    if title:
        return title
    labeled = _label_of(raw.get("labels"))
    if labeled:
        return labeled
    return str(raw.get("id") or raw.get("qa_group_id") or "").strip()


def luna_title_fields(raw: dict[str, Any]) -> dict[str, str]:
    """Fields Luna sees at customer-message time. Empty AI fields stay empty (legacy fallback)."""
    original = original_title_of(raw)
    ai_title = str(raw.get("ai_search_title") or "").strip()
    ai_desc = str(raw.get("ai_search_description") or "").strip()
    notes_snip = str(raw.get("notes") or raw.get("short_introduction") or "")[:240]
    return {
        "original_title": original,
        "title": original,
        "ai_search_title": ai_title,
        "ai_search_description": ai_desc,
        "description": ai_desc or notes_snip,
    }
