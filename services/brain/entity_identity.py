"""Canonical service/product identity. Overlapping names are not the same entity."""

from __future__ import annotations

import re
from typing import Any

from services.brain.normalize import normalize_search_text

_BUNDLE_SPLIT = re.compile(r"\s*(?:\+|&&|&|,|/|\band\b| و )\s*", re.I)
_GENERIC = {
    "a",
    "an",
    "the",
    "for",
    "of",
    "and",
    "with",
    "your",
    "my",
    "is",
    "are",
    "how",
    "much",
    "price",
    "cost",
    "please",
    "service",
    "services",
    "product",
    "products",
    "package",
    "packages",
    "treatment",
    "treatments",
    "hair",
    "removal",
    "laser",
    "do",
    "you",
    "offer",
    "have",
    "what",
    "which",
    "سعر",
    "كلفة",
    "كم",
    "شو",
    "عندكن",
    "خدمات",
    "خدمة",
    "منتج",
    "منتجات",
}


def canonical_id(*values: Any) -> str:
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        if ":" in text:
            text = text.split(":", 1)[-1].strip() or text
        return text
    return ""


def is_bundle_name(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    if any(mark in text for mark in ("+", "&", "/")):
        return True
    return bool(re.search(r"\s(?:and|و)\s", text, re.I))


def _stems(token: str) -> set[str]:
    forms = {token}
    if token.endswith("s") and len(token) > 3:
        forms.add(token[:-1])
    else:
        forms.add(f"{token}s")
    return forms


def distinctive_tokens(text: str) -> list[str]:
    tokens = [tok for tok in normalize_search_text(text).split() if tok and tok not in _GENERIC and len(tok) > 1]
    return list(dict.fromkeys(tokens))


def score_label(query: str, label: str, *, aliases: list[str] | tuple[str, ...] = ()) -> float:
    """Rank a published label against a customer question. Generic tokens are not enough."""
    needle = normalize_search_text(query)
    title = normalize_search_text(label)
    if not needle or not title:
        return 0.0
    if needle == title:
        return 100.0
    alias_norm = [normalize_search_text(item) for item in aliases if str(item).strip()]
    if any(item and item == needle for item in alias_norm):
        return 94.0
    if title in needle or needle in title:
        bonus = 12.0 if not is_bundle_name(label) else 0.0
        return 80.0 + bonus
    if any(item and (item in needle or needle in item) for item in alias_norm):
        return 72.0
    q_tokens = distinctive_tokens(query)
    t_tokens = distinctive_tokens(label)
    if not q_tokens or not t_tokens:
        return 0.0
    q_stems = {stem for tok in [*q_tokens, *needle.split()] for stem in _stems(tok)}
    overlap = [tok for tok in t_tokens if _stems(tok) & q_stems]
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(t_tokens)
    if coverage < 1.0 and len(t_tokens) > 1:
        # Partial title overlap is weak unless the query names that whole title.
        if not all(tok in needle for tok in t_tokens):
            coverage *= 0.45
    score = 40.0 + (coverage * 40.0)
    if is_bundle_name(label) and coverage < 1.0:
        score -= 18.0
    if not is_bundle_name(label) and all(tok in needle for tok in t_tokens):
        score += 16.0
    return max(0.0, score)


def prefer_standalone(query: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """When the customer names a standalone entity, do not silently pick a broader bundle."""
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for row in rows:
        title = str(row.get("title") or row.get("name") or row.get("label") or "")
        aliases = row.get("aliases") or []
        if not isinstance(aliases, (list, tuple)):
            aliases = []
        ranked.append((score_label(query, title, aliases=list(aliases)), 0 if is_bundle_name(title) else 1, row))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    if not ranked or ranked[0][0] < 28.0:
        return None
    winner = ranked[0][2]
    if not is_bundle_name(str(winner.get("title") or winner.get("name") or "")):
        return winner
    standalone = next((item for _score, standalone_flag, item in ranked if standalone_flag and _score >= 28.0), None)
    return standalone or winner
