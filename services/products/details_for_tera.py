"""Tera-facing product details: selected product only, no media dump."""

from __future__ import annotations

from typing import Any

from services.products.availability import normalize_availability
from services.products.schemas import product_to_dict


def product_details_for_tera(row: Any) -> dict[str, Any]:
    raw = product_to_dict(row)
    images = list(raw.get("images") or [])
    links = list(raw.get("links") or [])
    video_count = sum(1 for link in links if str(link.get("label") or "") == "asset:video")
    image_count = 0
    tenant_id = str(raw.get("tenant_id") or getattr(row, "tenant_id", "") or "")
    from services.products.media import load_media_meta

    for img in images:
        media_id = str((img or {}).get("media_id") or "")
        mime = str((load_media_meta(tenant_id=tenant_id, media_id=media_id) or {}).get("mime") or "").lower()
        if mime.startswith("video/"):
            video_count += 1
        else:
            image_count += 1
    availability = normalize_availability(raw.get("availability"))
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "title": raw.get("name"),
        "price": raw.get("price"),
        "currency": raw.get("currency"),
        "colors": raw.get("colors") or [],
        "sizes": raw.get("sizes") or [],
        "notes": raw.get("note") or raw.get("notes"),
        "availability": availability,
        "status": availability,
        "in_stock": availability == "in_stock",
        "image_count": image_count,
        "video_count": video_count,
        "related_services": raw.get("related_services") or [],
        "related_requests": raw.get("related_requests") or [],
    }
