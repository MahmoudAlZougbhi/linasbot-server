"""Conversation router KEEP: human-request detect only."""

from __future__ import annotations

import re

from services.brain.conversation_router_patterns import HUMAN_REQUEST_KEYWORDS, HUMAN_REQUEST_RE


def _normalize(text: str) -> str:
    return (text or "").strip()


def is_human_request(message: str) -> bool:
    """Detect if user wants to speak with a human/agent/employee."""
    t = _normalize(message)
    if len(t) < 3:
        return False
    # Personal-care / product questions containing "person" must not escalate.
    t_lower = t.lower()
    if re.search(r"\bpersonal\b", t_lower) and not re.search(
        r"\b(?:real\s+person|speak|talk|human\s+agent)\b", t_lower
    ):
        return False
    if HUMAN_REQUEST_RE.search(t):
        return True
    return any(kw in t_lower for kw in HUMAN_REQUEST_KEYWORDS)
