"""Window owner-chat history for a Sol turn (last N, optional char clip)."""

from __future__ import annotations

from typing import Any

from services.runtime_limits.defaults import RuntimeLimits
from services.runtime_limits.loader import load_runtime_limits


def clip_chars(text: str, max_chars: int) -> str:
    """Clip only when max_chars > 0. 0 / unset = full message (no 600 default)."""
    t = text or ""
    if max_chars <= 0 or len(t) <= max_chars:
        return t
    if max_chars == 1:
        return "…"
    return t[: max_chars - 1] + "…"


def window_owner_messages(
    messages: list[dict[str, Any]] | None,
    *,
    n: int,
    max_chars: int = 0,
) -> list[dict[str, Any]]:
    """Keep the last N owner↔Sol messages. Do not hydrate an unbounded archive into the pack."""
    cap = max(1, int(n))
    sliced = list(messages or [])[-cap:]
    out: list[dict[str, Any]] = []
    for raw in sliced:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "")
        content = clip_chars(str(raw.get("content") or ""), max_chars)
        row: dict[str, Any] = {"role": role, "content": content}
        if raw.get("tool_calls"):
            row["tool_calls"] = raw["tool_calls"]
        out.append(row)
    return out


def window_owner_messages_for_tenant(
    messages: list[dict[str, Any]] | None,
    tenant_id: str,
    *,
    limits: RuntimeLimits | None = None,
) -> list[dict[str, Any]]:
    lim = limits or load_runtime_limits(tenant_id)
    return window_owner_messages(
        messages,
        n=lim.owner_history_messages,
        max_chars=lim.owner_message_max_chars,
    )
