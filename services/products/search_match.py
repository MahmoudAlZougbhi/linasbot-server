"""Tenant product search: partial names, typos, and stored aliases."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher
from typing import Any


def match_products(query: str, products: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    needle = _norm(query)
    if not needle:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for product in products:
        names = [str(product.get("name") or "")]
        names.extend(str(item) for item in product.get("aliases") or [])
        best = 0.0
        for name in names:
            hay = _norm(name)
            if not hay:
                continue
            if hay in needle or needle in hay:
                best = max(best, 0.99)
            else:
                best = max(best, SequenceMatcher(None, needle, hay).ratio())
        if best >= 0.72:
            scored.append((best, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in scored[:limit]]


def media_facts(media: list[dict[str, str]]) -> dict[str, list[str]]:
    facts: dict[str, list[str]] = {"image": [], "video": [], "link": []}
    for item in media:
        kind = str(item.get("type") or "")
        url = str(item.get("url") or item.get("media_id") or "")
        if kind in facts and url:
            facts[kind].append(url)
    return facts


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(src, dst)
    return " ".join(text.casefold().split())
