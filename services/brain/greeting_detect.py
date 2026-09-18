"""Deterministic greeting-only detection. Does not author customer copy."""

from __future__ import annotations

import re
from datetime import timedelta

import config

GREETING_INACTIVITY_SECONDS = 43200  # 12 hours

_GREETING_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"hi+|hello|hey+|hola|"
    r"bonjour|salut|bonsoir|"
    r"مرحباً?|اهلاً?|أهلاً?|هلا|أهلين|"
    r"السلام عليكم|"
    r"صباح الخير|مساء الخير|"
    r"marhaba|mar7aba|hiya"
    r")"
    r"(?:\s+(?:kifak|keefak|كيفك|كيف حالك|how are you|ça va|ca va))?"
    r"\s*(?:[!?.؟]+)?\s*(?:👋|😊|🌷)?\s*$",
    re.IGNORECASE | re.UNICODE,
)


def inactivity_threshold() -> timedelta:
    """Use the existing Meta DM 12-hour constant; do not invent a new window."""
    seconds = int(GREETING_INACTIVITY_SECONDS)
    if seconds > 0:
        return timedelta(seconds=seconds)
    hours = int(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
    return timedelta(hours=max(hours, 0))


def inbound_greeting_language(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "en"
    try:
        from services.owner_copilot.system_knowledge_retrieval import detect_message_language

        code = detect_message_language(text, fallback="en")
        if code in {"ar", "franco"}:
            return "ar"
        if code in {"en", "fr"}:
            return code
    except Exception:
        pass
    return "en"


def is_greeting_only(message: str) -> bool:
    """True for hello / marhaba kifak with no hours, price, or booking ask."""
    return bool(_GREETING_ONLY_RE.match((message or "").strip()))
