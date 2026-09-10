"""Exact FAQ cannot serve stale prices/hours just because the question matches."""

from __future__ import annotations

import re

from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import LexicalHit

_DYNAMIC = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(usd|lbp|eur|gbp|\$|€)|"
    r"\b\d{1,2}:\d{2}\b|"
    r"\b(am|pm|صباحا|مساء)\b|"
    r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b)",
    re.I,
)


def looks_like_dynamic_fact(answer: str) -> bool:
    return bool(_DYNAMIC.search(answer or ""))


def current_sources_support(answer: str, tenant_id: str) -> bool:
    tid = (tenant_id or "").strip()
    if not tid:
        return False
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return False
    cards = [card for card in cards_from_sections(sections) if card.source_family in {"prices", "hours", "services"}]
    if not cards:
        return False
    bundle = expand_hits([LexicalHit(card=card, score=1.0) for card in cards[:12]], sections)
    hay = "\n".join(item.text for item in bundle.items).lower()
    tokens = {match.group(0).lower().strip() for match in _DYNAMIC.finditer(answer or "")}
    if not tokens:
        return True
    return all(token in hay for token in tokens)


def faq_static_allowed(answer: str, *, tenant_id: str) -> bool:
    if not looks_like_dynamic_fact(answer):
        return True
    return current_sources_support(answer, tenant_id)
