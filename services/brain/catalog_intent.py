"""Customer-token catalog filters. Planner GPT chooses retrieve families — not regex."""

from __future__ import annotations

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


def catalog_filter_tokens(message: str) -> list[str]:
    """Tokens the customer actually said, minus universal stopwords."""
    from services.brain.normalize import normalize_search_text

    tokens = [tok for tok in normalize_search_text(message).split() if tok and tok not in _FILTER_STOP and len(tok) > 2]
    return list(dict.fromkeys(tokens))[:8]
