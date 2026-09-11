"""Bounded conversation carry-over for follow-up turns (no full-history stuffing)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_BRANCH = re.compile(r"\b(antelias|beirut|hamra|verdun|dbayeh|jounieh|branch)\b", re.I)
_AUDIENCE = re.compile(r"\b(men|women|male|female|للرجال|للنساء)\b", re.I)
_FOLLOWUP = re.compile(r"^(and|what about|how about|for|in|و|شو عن)\b", re.I)


@dataclass(frozen=True)
class ConversationResolution:
    rewritten_query: str
    used_turns: tuple[dict[str, str], ...]
    carry: dict[str, str]


def resolve_followup_query(
    message: str,
    history: list[Any] | tuple[Any, ...] | None,
    *,
    max_turns: int = 4,
) -> ConversationResolution:
    text = (message or "").strip()
    turns: list[dict[str, str]] = []
    for item in list(history or [])[-max_turns:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "")
            body = str(item.get("text") or item.get("content") or "").strip()
        else:
            role = str(getattr(item, "role", "") or "")
            body = str(getattr(item, "text", "") or "").strip()
        if body:
            turns.append({"role": role, "text": body})
    carry: dict[str, str] = {}
    scan_texts = [turn["text"] for turn in turns] + [text]
    for body in scan_texts:
        branch = _BRANCH.search(body)
        if branch:
            carry["branch"] = branch.group(1).lower()
        audience = _AUDIENCE.search(body)
        if audience:
            carry["audience"] = audience.group(1).lower()
        if "laser" in body.lower() or "full body" in body.lower():
            carry.setdefault("service", "laser")
    rewritten = text
    if _FOLLOWUP.match(text) or text.endswith("?") and len(text.split()) <= 6:
        bits = [text]
        if carry.get("service"):
            bits.append(carry["service"])
        if carry.get("branch"):
            bits.append(carry["branch"])
        if carry.get("audience"):
            bits.append(carry["audience"])
        rewritten = " ".join(bits)
    return ConversationResolution(rewritten_query=rewritten, used_turns=tuple(turns), carry=carry)
