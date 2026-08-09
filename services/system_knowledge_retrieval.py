"""Targeted System Knowledge retrieval for a single owner-chat turn."""

from __future__ import annotations

import re
from typing import Any

from services.system_knowledge_registry import CAPABILITIES, Capability, get_capability


def retrieve_capabilities(
    query: str,
    *,
    limit: int = 4,
    tags: frozenset[str] | None = None,
) -> list[Capability]:
    """Score capabilities by keyword/tag overlap; return a small targeted set."""
    text = (query or "").strip().lower()
    if not text:
        # Minimal default: core + cm overview only.
        core = [c for c in CAPABILITIES if "core" in c.tags or c.feature == "content_management"]
        return core[:limit]

    scored: list[tuple[int, Capability]] = []
    for cap in CAPABILITIES:
        if tags is not None and tags and not tags.intersection(cap.tags):
            continue
        score = 0
        for kw in cap.keywords:
            if kw.lower() in text:
                score += 3
        for tag in cap.tags:
            if tag.lower() in text:
                score += 1
        if cap.feature.replace("_", " ") in text:
            score += 4
        if cap.route in text.split():
            score += 2
        if score:
            scored.append((score, cap))

    scored.sort(key=lambda item: (-item[0], item[1].feature))
    if not scored:
        help_cap = get_capability("system_copilot")
        return [help_cap] if help_cap else []
    return [c for _, c in scored[: max(1, limit)]]


def capabilities_as_prompt_block(caps: list[Capability]) -> str:
    """Compact prompt fragment — not full docs."""
    if not caps:
        return ""
    lines = ["Relevant product capabilities (targeted):"]
    for cap in caps:
        block = (
            f"- {cap.feature} [{cap.status}] route={cap.route}"
            f" entitlement={cap.entitlement or 'none'}: {cap.description}"
        )
        if cap.blockers:
            block += f" Blockers: {'; '.join(cap.blockers)}"
        if cap.help_steps:
            block += " Steps: " + " | ".join(cap.help_steps[:3])
        lines.append(block)
    return "\n".join(lines)


def help_payload_for_query(query: str) -> dict[str, Any]:
    caps = retrieve_capabilities(query, limit=6)
    return {
        "capabilities": [c.to_public() for c in caps],
        "note": "CM setup is one capability of Linas AI, not the whole product.",
    }


_LANG_HINT = re.compile(r"[\u0600-\u06FF]")


def detect_message_language(text: str, *, fallback: str = "en") -> str:
    """Lightweight reply-language hint from the user message (not gender/name inference)."""
    raw = (text or "").strip()
    if not raw:
        return fallback if fallback in {"ar", "en", "fr"} else "en"
    if _LANG_HINT.search(raw):
        return "ar"
    lower = raw.lower()
    fr_markers = ("bonjour", "merci", "comment", "s'il", "vous", "abonnement", "utilisation")
    if any(m in lower for m in fr_markers):
        return "fr"
    return "en"
