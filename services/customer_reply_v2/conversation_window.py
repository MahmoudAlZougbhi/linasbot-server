"""Rolling DM conversation window (time-based, not last-N / not 600-char).

Default window is 90 minutes under Customer AI V10 (CUSTOMER_AI_V10_RUNTIME).
"""

from __future__ import annotations

import time
from typing import Any

from services.customer_reply_v2.flags import customer_context_token_budget, dm_context_window_hours
from services.customer_reply_v2.models import ConversationMessage, ConversationWindow

# Rough token estimate for emergency compaction only (not a normal message-count cap).
_CHARS_PER_TOKEN = 4
_PRESERVE_NEWEST_VERBATIM = 8


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _msg_timestamp(raw: dict[str, Any], fallback: float) -> float:
    for key in ("timestamp", "ts", "created_at", "time"):
        val = raw.get(key)
        if val is None:
            continue
        try:
            ts = float(val)
            if ts > 1e12:  # ms
                ts = ts / 1000.0
            return ts
        except (TypeError, ValueError):
            pass
        if isinstance(val, str) and val.strip():
            try:
                from datetime import datetime

                return datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return fallback


def filter_rolling_window(
    raw_messages: list[dict[str, Any]],
    *,
    now_ts: float | None = None,
    window_hours: float | None = None,
) -> ConversationWindow:
    """Include every message whose timestamp falls inside the rolling window.

    No fixed message-count limit. Long bodies are preserved (no 600-char truncate).
    """
    now = now_ts if now_ts is not None else time.time()
    hours = float(window_hours if window_hours is not None else dm_context_window_hours())
    cutoff = now - (hours * 3600.0)
    inside: list[ConversationMessage] = []
    outside = 0
    for i, raw in enumerate(raw_messages or []):
        role = str(raw.get("role") or "user").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(raw.get("content") or "")
        # Do not truncate normal messages.
        ts = _msg_timestamp(raw, fallback=now - (len(raw_messages) - i))
        if ts < cutoff:
            outside += 1
            continue
        if ts > now + 60:  # clock skew tolerance
            continue
        inside.append(ConversationMessage(role=role, content=content, timestamp=ts))  # type: ignore[arg-type]

    inside.sort(key=lambda m: m.timestamp or 0.0)
    compacted = False
    summary = ""
    budget = customer_context_token_budget()
    total = sum(_estimate_tokens(m.content) for m in inside)
    if total > budget and len(inside) > _PRESERVE_NEWEST_VERBATIM:
        keep = inside[-_PRESERVE_NEWEST_VERBATIM:]
        older = inside[:-_PRESERVE_NEWEST_VERBATIM]
        # Compact oldest into a structured summary — emergency only.
        bits = []
        for m in older:
            snippet = m.content.replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "…"
            bits.append(f"{m.role}: {snippet}")
        summary = " | ".join(bits)
        inside = keep
        compacted = True

    return ConversationWindow(
        messages=inside,
        window_hours=hours,
        context_compacted=compacted,
        compacted_summary=summary,
        excluded_outside_window=outside,
    )


async def load_dm_conversation_window(
    *,
    user_id: str,
    conversation_id: str,
    alternate_user_id: str | None = None,
    now_ts: float | None = None,
    window_hours: float | None = None,
    injected_messages: list[dict[str, Any]] | None = None,
) -> ConversationWindow:
    """Load DM history for the rolling window. Injected messages used by tests/fixtures."""
    if injected_messages is not None:
        return filter_rolling_window(injected_messages, now_ts=now_ts, window_hours=window_hours)

    from utils.utils import get_conversation_history_from_firestore

    hours = float(window_hours if window_hours is not None else dm_context_window_hours())
    # Fetch with generous lookback; filter_rolling_window applies the precise boundary.
    # max_messages=0 means no hard count cap in Firestore helper.
    try:
        history = await get_conversation_history_from_firestore(
            user_id,
            conversation_id,
            max_messages=0,
            window_hours=int(max(1, round(hours))),
            alternate_user_id=alternate_user_id,
            include_metadata=True,
        )
    except Exception:
        history = []

    # Firestore helper already time-filters but may use int hours; re-filter precisely.
    # Attach synthetic timestamps if missing so boundary tests with injected data still work.
    enriched: list[dict[str, Any]] = []
    now = now_ts if now_ts is not None else time.time()
    for i, msg in enumerate(history or []):
        row = dict(msg)
        if "timestamp" not in row and "created_at" not in row:
            row["timestamp"] = now - (len(history) - i)  # preserve order inside window
        enriched.append(row)
    return filter_rolling_window(enriched, now_ts=now_ts, window_hours=window_hours)
