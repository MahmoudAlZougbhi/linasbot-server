"""Bounded conversation carry-over for follow-up turns (no keyword rewrite)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationResolution:
    rewritten_query: str
    used_turns: tuple[dict[str, str], ...]
    carry: dict[str, str]


def _turns(history: list[Any] | tuple[Any, ...] | None, max_turns: int) -> list[dict[str, str]]:
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
    return turns


def resolve_followup_query(
    message: str,
    history: list[Any] | tuple[Any, ...] | None,
    *,
    max_turns: int = 4,
    tenant_id: str = "",
) -> ConversationResolution:
    """Pass the raw inbound plus recent history. Planner/Terra see the customer text as written."""
    _ = tenant_id
    text = (message or "").strip()
    turns = _turns(history, max_turns)
    return ConversationResolution(rewritten_query=text, used_turns=tuple(turns), carry={})
