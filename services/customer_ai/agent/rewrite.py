"""Query rewrite for Customer Brain: deterministic first, optional light LLM."""

from __future__ import annotations

import os
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


async def _optional_llm(message: str, history: list[Any] | None, language: str) -> str | None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        return None
    try:
        from services.customer_ai.providers.config import answer_model
        from services.llm_core_service import create_chat_completion

        hist = "\n".join(
            f"{getattr(m, 'role', m.get('role') if isinstance(m, dict) else '')}: "
            f"{getattr(m, 'text', m.get('text') if isinstance(m, dict) else '')}"
            for m in list(history or [])[-4:]
        )
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Rewrite for search only. Keep phones, prices, URLs, IDs unchanged. "
                        f"Language: {language or 'auto'}\nHistory:\n{hist}\nQuery: {message}"
                    ),
                }
            ],
            max_tokens=120,
        )
        text = str(response.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None


async def rewrite_queries(
    message: str,
    history: list[Any] | tuple[Any, ...] | None = None,
    language: str = "",
) -> dict[str, Any]:
    """Return {original, rewritten, variants}. LLM optional; failures stay deterministic."""
    base = _deterministic(message, list(history or []), language)
    held_surfaces = base.pop("held", [])
    llm = await _optional_llm(base["original"], list(history or []), language)
    if llm:
        ok = all((surface in llm) for surface in held_surfaces if surface.strip())
        if ok:
            base["rewritten"] = llm
            if llm not in base["variants"] and llm != base["original"]:
                base["variants"] = [llm, *base["variants"]]
    return {
        "original": base["original"],
        "rewritten": base["rewritten"],
        "variants": list(base["variants"]),
        "carry": dict(base.get("carry") or {}),
    }
