"""Shared CSV/XLSX import row parsing for AI Products."""

from __future__ import annotations

from typing import Any

from services.products.availability import AVAILABILITY_IN_STOCK, normalize_availability

_HEADER_ALIASES = {
    "product name": "name",
    "name": "name",
    "title": "name",
    "price": "price",
    "currency": "currency",
    "sizes": "sizes",
    "colors": "colors",
    "note": "note",
    "availability": "availability",
    "image url 1": "image_url_1",
    "image url 2": "image_url_2",
    "image url 3": "image_url_3",
    "tiktok url": "tiktok_url",
    "instagram url": "instagram_url",
    "facebook url": "facebook_url",
    "website url": "website_url",
    "website": "website_url",
}


def normalize_header(header: str) -> str:
    key = str(header or "").strip().lower()
    return _HEADER_ALIASES.get(key, key.replace(" ", "_"))


def normalize_import_row(raw: dict[str, Any], *, row_number: int) -> dict[str, Any]:
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        norm_key = normalize_header(str(key))
        normalized[norm_key] = str(value or "").strip()

    name = normalized.get("name") or ""
    sizes = [s.strip() for s in (normalized.get("sizes") or "").replace("|", ",").split(",") if s.strip()]
    colors = [c.strip() for c in (normalized.get("colors") or "").replace("|", ",").split(",") if c.strip()]
    price = normalized.get("price") or None
    currency = normalized.get("currency") or None
    if price and currency and currency.upper() not in price.upper():
        price = f"{price} {currency}"

    image_urls = [
        u
        for u in [
            normalized.get("image_url_1") or "",
            normalized.get("image_url_2") or "",
            normalized.get("image_url_3") or "",
        ]
        if u
    ][:3]

    links: list[dict[str, Any]] = []
    for field, label in {
        "tiktok_url": "TikTok",
        "instagram_url": "Instagram",
        "facebook_url": "Facebook",
        "website_url": "Website",
    }.items():
        url = normalized.get(field) or ""
        if url:
            links.append({"url": url, "label": label, "sort_order": len(links)})

    availability = normalize_availability(normalized.get("availability"), default=AVAILABILITY_IN_STOCK)
    preview: dict[str, Any] = {
        "row": row_number,
        "name": name,
        "price": price,
        "sizes": sizes,
        "colors": colors,
        "note": normalized.get("note") or None,
        "availability": availability,
        "image_urls": image_urls,
        "links": links,
    }
    if not name:
        preview["valid"] = False
        preview["error"] = "missing_name"
    else:
        preview["valid"] = True
    return preview


def import_template_headers() -> list[str]:
    return [
        "Product Name",
        "Price",
        "Currency",
        "Sizes",
        "Colors",
        "Note",
        "Availability",
        "Image URL 1",
        "Image URL 2",
        "Image URL 3",
        "TikTok URL",
        "Instagram URL",
        "Facebook URL",
        "Website URL",
    ]
