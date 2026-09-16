"""Customer-facing outbound must never be raw SOP / model instructions."""

from __future__ import annotations

import re

_MAX_OPENER_CHARS = 240

_INSTRUCTION_PHRASES = (
    "use this rule only",
    "arabic-specific rule",
    "greeting requirements",
    "do not use latin",
    "if the user message is not a casual greeting",
    "if the user message is only a casual greeting",
    "process the message according to",
    "owner_opener_note:",
    "system prompt",
    "never invent",
    "do not collect name",
)

_INSTRUCTION_RE = re.compile(
    r"("
    r"\bINTERNAL\b"
    r"|\bSYSTEM\b\s*:"
    r"|Arabic-specific rule"
    r"|Use this rule only"
    r"|Greeting requirements"
    r"|Do not use Latin"
    r")",
    re.I,
)

_IMPERATIVE_HITS = (
    "you must",
    "do not",
    "only if the user",
    "if the user message",
    "follow this rule",
    "this rule applies",
)


def looks_like_instruction_text(text: str) -> bool:
    """True when text is model/SOP instructions, not a customer reply."""
    body = (text or "").strip()
    if not body:
        return False
    if _INSTRUCTION_RE.search(body):
        return True
    lowered = body.lower()
    if any(phrase in lowered for phrase in _INSTRUCTION_PHRASES):
        return True
    hits = sum(1 for needle in _IMPERATIVE_HITS if needle in lowered)
    latin = sum(1 for ch in body if "a" <= ch.lower() <= "z")
    other = sum(1 for ch in body if ch.isalpha() and not ("a" <= ch.lower() <= "z"))
    mostly_english = latin >= 40 and latin > other * 2
    return mostly_english and hits >= 2


def is_customer_safe_opener(text: str) -> bool:
    """Short natural greeting/opener. Rejects SOP and instruction dumps."""
    body = (text or "").strip()
    if not body or len(body) > _MAX_OPENER_CHARS:
        return False
    if body.count("\n") > 2:
        return False
    return not looks_like_instruction_text(body)


def is_llm_provider_error(exc: BaseException) -> bool:
    """OpenAI/http transport failures — fail-soft, not the catch-all Exception path."""
    try:
        from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, RateLimitError

        if isinstance(
            exc,
            (APIError, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError, TimeoutError),
        ):
            return True
    except Exception:
        pass
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    if name in {
        "APIError",
        "APIConnectionError",
        "APITimeoutError",
        "APIStatusError",
        "RateLimitError",
        "AuthenticationError",
        "InternalServerError",
        "TimeoutError",
    }:
        return True
    return module.startswith("openai") or module.startswith("httpx")
