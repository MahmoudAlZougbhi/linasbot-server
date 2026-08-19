"""Apply save-time Luna metadata to one Product row only."""

from __future__ import annotations

import json
from typing import Any

from services.products.schemas import normalize_product_name
from services.search_metadata.fingerprint import content_fingerprint
from services.search_metadata.generate import (
    SearchMetadata,
    generate_search_metadata,
    is_weak_owner_description,
)

_LAST_PRODUCT_APPLY: dict[str, Any] = {"product_id": "", "generated": False}


def last_product_apply_stats() -> dict[str, Any]:
    return dict(_LAST_PRODUCT_APPLY)


def product_content_payload(row: Any) -> dict[str, Any]:
    keywords = getattr(row, "ai_search_keywords", None)
    return {
        "name": getattr(row, "name", "") or "",
        "description": getattr(row, "description", None) or "",
        "price": getattr(row, "price", None) or "",
        "sizes": list(getattr(row, "sizes", None) or []),
        "colors": list(getattr(row, "colors", None) or []),
        "note": getattr(row, "note", None) or "",
        "availability": getattr(row, "availability", None) or "",
        "ai_search_title": getattr(row, "ai_search_title", None) or "",
        "ai_search_description": getattr(row, "ai_search_description", None) or "",
        "ai_search_keywords": list(keywords) if isinstance(keywords, list) else [],
    }


def product_grounded_content(row: Any) -> str:
    payload = product_content_payload(row)
    payload.pop("ai_search_title", None)
    payload.pop("ai_search_description", None)
    payload.pop("ai_search_keywords", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def enrich_product_row(row: Any, *, previous: dict[str, Any] | None = None) -> bool:
    """Regenerate English search metadata for this product only. Returns True if Luna ran."""
    current = product_content_payload(row)
    _LAST_PRODUCT_APPLY.update({"product_id": str(getattr(row, "id", "") or ""), "generated": False})
    if previous is not None and content_fingerprint(current) == content_fingerprint(previous):
        return False
    weak = is_weak_owner_description(str(current.get("description") or ""))
    meta = generate_search_metadata(
        {
            "kind": "product",
            "section": "products",
            "item_id": str(getattr(row, "id", "") or ""),
            "original_title": str(current.get("name") or ""),
            "content": product_grounded_content(row),
            "include_keywords": True,
            "weak_description": weak,
        }
    )
    if weak:
        meta = _weaken_product_meta(meta, name=str(current.get("name") or ""))
        from services.search_metadata.validate import require_ready_metadata

        require_ready_metadata(
            meta,
            include_keywords=True,
            content=product_grounded_content(row),
            original_title=str(current.get("name") or ""),
        )
    _apply_meta(row, meta)
    _LAST_PRODUCT_APPLY["generated"] = True
    return True


def _weaken_product_meta(meta: SearchMetadata, *, name: str) -> SearchMetadata:
    """Do not invent category/use when the owner description is unusable.

    Keywords may be empty after stripping invented terms. Title and description
    stay required English strings (never empty).
    """
    lowered = f"{meta.title} {meta.description} {' '.join(meta.keywords)}".lower()
    invented = any(
        token in lowered
        for token in (
            "face cream",
            "body lotion",
            "shampoo",
            "moisturizer",
            "moisturising",
            "moisturizing",
            "headset",
            "laser",
            "skincare",
            "skin care",
        )
    )
    name_l = name.lower()
    if invented and not any(token in name_l for token in ("cream", "lotion", "shampoo", "headset", "laser")):
        safe_title = name if not _has_non_latin(name) else "Catalog product"
        return SearchMetadata(
            title=safe_title,
            description="Named catalog product. Owner description is not specific.",
            keywords=[],
        )
    return meta


def _has_non_latin(text: str) -> bool:
    from services.search_metadata.english import contains_non_english_script

    return contains_non_english_script(text)


def _apply_meta(row: Any, meta: SearchMetadata) -> None:
    row.ai_search_title = meta.title or None
    row.ai_search_description = meta.description or None
    row.ai_search_keywords = list(meta.keywords or []) or None
    row.ai_search_title_normalized = normalize_product_name(meta.title) if meta.title else None
