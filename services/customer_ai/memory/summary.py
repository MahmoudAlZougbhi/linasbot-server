"""Rolling summary of older-than-visible messages (bounded string)."""

from __future__ import annotations

from typing import Any

_MAX_CHARS = 600
_MAX_LINES = 8


def rolling_summary(
    messages: list[Any] | tuple[Any, ...] | None,
    *,
    visible_cap: int = 50,
    keep_visible: int | None = None,
    max_chars: int = _MAX_CHARS,
) -> str:
    """Summarize messages older than the visible window into a bounded string."""
    cap = keep_visible if keep_visible is not None else visible_cap
    rows = list(messages or [])
    if len(rows) <= cap:
        return ""
    older = rows[:-cap]
    lines: list[str] = []
    for item in older[-(_MAX_LINES * 2) :]:
        if isinstance(item, dict):
            role = str(item.get("role") or "user")
            text = str(item.get("text") or item.get("content") or "").strip()
        else:
            role = str(getattr(item, "role", "") or "user")
            text = str(getattr(item, "text", "") or "").strip()
        if text:
            lines.append(f"{role}: {text[:120]}")
    if not lines:
        return ""
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        if len(kept) >= _MAX_LINES:
            break
        if total + len(line) + 1 > max_chars:
            break
        kept.append(line)
        total += len(line) + 1
    kept.reverse()
    return " | ".join(kept)[:max_chars]
