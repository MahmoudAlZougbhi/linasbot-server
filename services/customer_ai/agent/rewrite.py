"""Query rewrite for Customer Brain: deterministic (no extra LLM on the live path)."""

from __future__ import annotations

import re
from typing import Any

from services.customer_ai.conversation_resolve import resolve_followup_query

_PROTECTED = re.compile(
    r"("
    r"(?:https?://|www\.)[^\s<>\"'`]+"
    r"|\+?\d[\d\s\-().]{5,}\d"
    r"|(?:\$|€|£)?\s*\d+(?:[.,]\d+)?\s*(?:usd|lbp|eur|gbp|\$|€)?"
    r"|\b(?:id|sku|ref)[:\s#-]*[A-Za-z0-9_-]{3,}\b"
    r")",
    re.I,
)
_NOISE = re.compile(
    r"\b(please|pls|can you|could you|tell me|i want|i need|بدي|ممكن|شو|كيف)\b",
    re.I,
)


def _protect(text: str) -> tuple[str, list[str]]:
    held: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f" __P{len(held) - 1}__ "

    return _PROTECTED.sub(_keep, text or ""), held


def _restore(text: str, held: list[str]) -> str:
    out = text
    for index, value in enumerate(held):
        out = out.replace(f"__P{index}__", value)
    return " ".join(out.split())


def _deterministic(message: str, history: list[Any] | None, language: str) -> dict[str, Any]:
    original = (message or "").strip()
    resolved = resolve_followup_query(original, history)
    protected, held = _protect(resolved.rewritten_query or original)
    cleaned = _NOISE.sub(" ", protected)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?!.،؟")
    if language.lower().startswith("ar") and "سعر" not in cleaned.lower():
        if re.search(r"\b(price|cost|how much|se3er|seer)\b", original, re.I):
            cleaned = f"{cleaned} سعر".strip()
    rewritten = _restore(cleaned, held) or original
    variants: list[str] = []
    for item in (rewritten,):
        if item and item != original:
            variants.append(item)
    for key in ("branch", "service", "audience"):
        value = resolved.carry.get(key)
        if value and value not in rewritten.lower():
            variants.append(f"{rewritten} {value}".strip())
    seen: set[str] = set()
    unique: list[str] = []
    for item in variants:
        key = item.casefold()
        if key and key not in seen and item != original:
            seen.add(key)
            unique.append(item)
    return {
        "original": original,
        "rewritten": rewritten,
        "variants": unique,
        "carry": dict(resolved.carry),
        "held": held,
    }


async def rewrite_queries(
    message: str,
    history: list[Any] | tuple[Any, ...] | None = None,
    language: str = "",
) -> dict[str, Any]:
    """Return {original, rewritten, variants}. Live path is deterministic (no extra LLM)."""
    base = _deterministic(message, list(history or []), language)
    base.pop("held", None)
    return {
        "original": base["original"],
        "rewritten": base["rewritten"],
        "variants": list(base["variants"]),
        "carry": dict(base.get("carry") or {}),
    }
