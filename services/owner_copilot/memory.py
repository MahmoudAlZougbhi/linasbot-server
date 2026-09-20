"""Token-aware durable conversation memory packing for Owner Copilot V2."""

from __future__ import annotations

from typing import Any

from services.runtime_limits.window import clip_chars


def _approx_tokens(text: str) -> int:
    return max(1, len((text or "").strip()) // 4)


def pack_recent_messages(
    messages: list[dict[str, Any]] | None,
    *,
    token_budget: int | None = None,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> tuple[list[dict[str, str]], str | None]:
    """Pack last N owner messages for Sol.

    Default is count-windowed (portal ``owner_history_messages``, typically 100).
    No 600-char per-message clip unless ``max_chars`` > 0.
    ``token_budget`` is an optional last-resort provider ceiling (only when passed).
    """
    msgs = list(messages or [])
    if not msgs:
        return [], None
    cap = int(max_messages) if max_messages is not None else len(msgs)
    cap = max(1, cap)
    window = msgs[-cap:]
    clip = int(max_chars or 0)
    selected: list[dict[str, str]] = []
    for m in window:
        role = str(m.get("role") or "").strip().lower()
        content = clip_chars(str(m.get("content") or "").strip(), clip)
        if role not in {"user", "assistant"} or not content:
            continue
        selected.append({"role": role, "content": content})
    if token_budget is None:
        return selected, _older_summary(msgs, kept=len(selected))
    budget = int(token_budget)
    recent: list[dict[str, str]] = []
    used = 0
    for m in reversed(selected):
        cost = _approx_tokens(m["content"]) + 4
        if recent and used + cost > budget:
            break
        recent.append(m)
        used += cost
    recent.reverse()
    return recent, _older_summary(msgs, kept=len(recent), budget=budget)


def _older_summary(
    msgs: list[dict[str, Any]],
    *,
    kept: int,
    budget: int | None = None,
) -> str | None:
    older = msgs[: max(0, len(msgs) - kept)]
    if not older:
        return None
    bits: list[str] = []
    for m in older[-12:]:
        role = str(m.get("role") or "?")
        content = str(m.get("content") or "").strip()
        if content:
            bits.append(f"{role}: {content[:160]}")
    if not bits:
        return None
    summary = "Earlier conversation (compressed):\n" + "\n".join(bits)
    if budget is None:
        return summary
    while _approx_tokens(summary) > max(200, budget // 4) and len(bits) > 2:
        bits = bits[1:]
        summary = "Earlier conversation (compressed):\n" + "\n".join(bits)
    return summary


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(_approx_tokens(str(m.get("content") or "")) + 4 for m in messages)
