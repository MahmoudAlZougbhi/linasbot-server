"""High-risk amount contradiction detection across evidence text."""

from __future__ import annotations

import re
from typing import Any

from services.customer_ai.grounding import extract

_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(usd|lbp|eur|gbp|\$|€)", re.I)


def detect_amount_contradictions(evidence_text: str) -> list[dict[str, Any]]:
    """If the same entity-ish window asserts different money amounts, flag conflict."""
    text = evidence_text or ""
    amounts = []
    for match in _AMOUNT.finditer(text):
        unit = match.group(2).lower().replace("$", "usd")
        amounts.append(f"{match.group(1)}|{unit}")
    unique = sorted(set(amounts))
    if len(unique) <= 1:
        return []
    # Multiple distinct amounts in one evidence blob → contradiction for price questions.
    return [{"type": "amount", "values": unique, "reason": "conflicting_amounts_in_evidence"}]


def detect_phone_contradictions(evidence_text: str) -> list[dict[str, Any]]:
    phones = sorted(extract.phones(evidence_text or ""))
    if len(phones) <= 1:
        return []
    return [{"type": "phone", "values": phones, "reason": "conflicting_phones_in_evidence"}]
