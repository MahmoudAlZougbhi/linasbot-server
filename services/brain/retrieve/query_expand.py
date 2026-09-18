"""Generic multilingual query expansion. Not a tenant/service dictionary."""

from __future__ import annotations

import re

# Cross-language *intent* synonyms only. Never branch names or a tenant catalog.
_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("خدمات", "services"),
    ("خدمة", "service"),
    ("منتجات", "products"),
    ("منتج", "product"),
    ("باقات", "packages"),
    ("باقة", "package"),
    ("اسعار", "prices"),
    ("سعر", "price"),
    ("دوام", "hours"),
    ("ساعات", "hours"),
    ("اوقات", "hours"),
    ("فرع", "branch"),
    ("فروع", "branches"),
    ("services", "خدمات"),
    ("products", "منتجات"),
    ("packages", "باقات"),
    ("price", "سعر"),
    ("hours", "دوام"),
    ("horaires", "hours"),
    ("produits", "products"),
    ("forfaits", "packages"),
    ("soins", "treatments"),
    ("khadamat", "خدمات"),
    ("khadamet", "خدمات"),
    ("se3er", "سعر"),
    ("dawem", "دوام"),
)


def expand_query_text(query: str) -> str:
    body = (query or "").strip()
    if not body:
        return ""
    extras: list[str] = []
    lowered = body.casefold()
    for src, dst in _SYNONYMS:
        if re.search(rf"(?<!\w){re.escape(src)}(?!\w)", lowered, re.I) or src in body:
            if dst.casefold() not in lowered:
                extras.append(dst)
    if not extras:
        return body
    return f"{body} {' '.join(dict.fromkeys(extras))}"
