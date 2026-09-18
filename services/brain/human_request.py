"""Detect an explicit ask for a human teammate. Does not author customer copy."""

from __future__ import annotations

import re

from services.brain.conversation_router_patterns import HUMAN_REQUEST_KEYWORDS, HUMAN_REQUEST_RE


def is_human_request(message: str) -> bool:
    """Detect if the customer wants to speak with a human/agent/employee."""
    text = (message or "").strip()
    if len(text) < 3:
        return False
    t_lower = text.lower()
    if re.search(r"\bpersonal\b", t_lower) and not re.search(
        r"\b(?:real\s+person|speak|talk|human\s+agent)\b", t_lower
    ):
        return False
    if HUMAN_REQUEST_RE.search(text):
        return True
    return any(keyword in t_lower for keyword in HUMAN_REQUEST_KEYWORDS)
