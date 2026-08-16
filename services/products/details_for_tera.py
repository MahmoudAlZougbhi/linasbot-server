"""Tera-facing product details: selected product only, no media dump."""

from __future__ import annotations

from typing import Any

from services.products.availability import normalize_availability
from services.products.schemas import product_to_dict


def product_details_for_tera(row: Any) -> dict[str, Any]:
    raw = product_to_dict(row)
    images = list(raw.get("images") or [])
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
        "image_count": len(images),
        "video_count": 0,
        "related_services": raw.get("related_services") or [],
        "related_requests": raw.get("related_requests") or [],
    }
