"""Deterministic claim checks against selected evidence. Not an LLM critic."""

from __future__ import annotations

import re

from services.customer_ai.contracts.evidence import EvidenceBundle

_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(usd|lbp|eur|gbp|\$|€)", re.I)


def _amounts(text: str) -> set[str]:
    found: set[str] = set()
    for match in _AMOUNT.finditer(text or ""):
        found.add(f"{match.group(1)}|{match.group(2).lower().replace('$', 'usd')}")
    return found


def ungrounded_amounts(reply_text: str, bundle: EvidenceBundle) -> list[str]:
    allowed: set[str] = set()
    for item in bundle.items:
        allowed |= _amounts(item.text)
    claimed = _amounts(reply_text)
    return sorted(claimed - allowed)


def evidence_supports_text(reply_text: str, bundle: EvidenceBundle) -> bool:
    text = (reply_text or "").strip()
    if not text or not bundle.items:
        return False
    if ungrounded_amounts(text, bundle):
        return False
    return True
