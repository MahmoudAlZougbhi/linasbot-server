"""Token-aware durable conversation memory packing for Owner Copilot V2."""

from __future__ import annotations

from typing import Any

from services.owner_copilot_v2.flags import owner_context_token_budget


def _approx_tokens(text: str) -> int:
    return max(1, len((text or "").strip()) // 4)


def pack_recent_messages(
    messages: list[dict[str, Any]] | None,
    *,
    token_budget: int | None = None,
) -> tuple[list[dict[str, str]], str | None]:
    """Select a recent-turn window by token budget (not fixed 8×600).

    Returns (recent_messages, optional_summary_of_older).
    """
    budget = int(token_budget or owner_context_token_budget() // 3)
    msgs = list(messages or [])
    if not msgs:
        return [], None

    recent: list[dict[str, str]] = []
    used = 0
    for m in reversed(msgs):
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cost = _approx_tokens(content) + 4
        if recent and used + cost > budget:
            break
        recent.append({"role": role, "content": content})
        used += cost
    recent.reverse()

    kept = len(recent)
    older = msgs[: max(0, len(msgs) - kept)]
    summary = None
    if older:
        bits: list[str] = []
        for m in older[-12:]:
            role = str(m.get("role") or "?")
            content = str(m.get("content") or "").strip()
            if content:
                bits.append(f"{role}: {content[:160]}")
        if bits:
            summary = "Earlier conversation (compressed):\n" + "\n".join(bits)
            # Trim summary to remaining budget slice
            while _approx_tokens(summary) > max(200, budget // 4) and len(bits) > 2:
                bits = bits[1:]
                summary = "Earlier conversation (compressed):\n" + "\n".join(bits)
    return recent, summary


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(_approx_tokens(str(m.get("content") or "")) + 4 for m in messages)
