"""Tenant-generic catalog/list intent. Do not treat a list ask as a single nearest card."""

from __future__ import annotations

import re

_LIST = re.compile(
    r"("
    r"\b(what|which|show|list|all)\b.{0,40}\b(services?|products?|packages?|treatments?|menus?|"
    r"plans?|items?|options?)\b"
    r"|\b(services?|products?|packages?|treatments?|menus?)\s+(do you|you offer|you have|available)\b"
    r"|شو\s+(ال)?(خدمات|منتجات|باقات|عروض)"
    r"|ما هي\s+(ال)?(خدمات|منتجات|باقات)"
    r"|عندكن\s+(خدمات|منتجات|باقات)"
    r"|الخدمات\s+(الموجودة|المتوفرة|اللي عندكن)"
    r"|quels?\s+(services|produits|forfaits|soins)"
    r"|vos\s+(services|produits|soins|forfaits)"
    r")",
    re.I | re.S,
)

_FILTER_STOP = {
    "what",
    "which",
    "show",
    "list",
    "all",
    "your",
    "you",
    "do",
    "offer",
    "have",
    "available",
    "existing",
    "the",
    "me",
    "please",
    "شو",
    "ما",
    "هي",
    "اللي",
    "عندكن",
    "الموجودة",
    "المتوفرة",
    "خدمات",
    "خدمة",
    "منتجات",
    "باقات",
    "عروض",
    "services",
    "service",
    "products",
    "product",
    "packages",
    "treatments",
}


def is_catalog_list(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_LIST.search(text))


def catalog_filter_tokens(message: str) -> list[str]:
    """Optional category words the customer actually said (laser, vegan, mens, …)."""
    from services.brain.normalize import normalize_search_text

    tokens = [tok for tok in normalize_search_text(message).split() if tok and tok not in _FILTER_STOP and len(tok) > 2]
    return list(dict.fromkeys(tokens))[:8]
