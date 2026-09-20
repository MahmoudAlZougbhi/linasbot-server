"""Exact latest-50 customer-visible history. Never silently summarize."""

from __future__ import annotations

from typing import Any

from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.contracts.turn import HistorySnapshot, VisibleMessage

_PRIVATE_ROLES = frozenset(
    {
        "system",
        "tool",
        "staff_note",
        "internal",
        "debug",
        "trace",
        "draft",
    }
)
_STAFF_VISIBLE = frozenset({"staff", "operator", "human", "agent"})
_ASSISTANT = frozenset({"assistant", "ai", "bot"})
_USER = frozenset({"user", "customer", "visitor"})


def _role_of(raw: dict[str, Any]) -> str:
    return str(raw.get("role") or raw.get("sender_role") or "").strip().lower()


def _visible(raw: dict[str, Any]) -> bool:
    if raw.get("visible_to_customer") is False:
        return False
    if raw.get("private_staff_note") or raw.get("internal") or raw.get("unsent"):
        return False
    role = _role_of(raw)
    if role in _PRIVATE_ROLES:
        return False
    if raw.get("kind") in {"internal_event", "trace", "debug"}:
        return False
    return role in _USER or role in _ASSISTANT or role in _STAFF_VISIBLE or not role


def _clip_text(text: str, max_chars: int | None) -> str:
    t = (text or "").strip()
    if not max_chars or max_chars <= 0 or len(t) <= max_chars:
        return t
    if max_chars == 1:
        return "…"
    return t[: max_chars - 1] + "…"


def _text_of(raw: dict[str, Any]) -> str:
    return str(raw.get("text") or raw.get("content") or raw.get("message") or "").strip()


def _id_of(raw: dict[str, Any], index: int) -> str:
    return str(raw.get("id") or raw.get("message_id") or f"msg:{index}")


def build_history_snapshot(
    raw_messages: list[dict[str, Any]] | None,
    *,
    current_inbound_id: str = "",
    current_inbound_text: str = "",
    cap: int | None = None,
    max_chars: int | None = None,
    tenant_id: str = "",
) -> HistorySnapshot:
    """Keep chronological customer-visible messages; cap is the latest N (default 50)."""
    clip = int(max_chars) if max_chars is not None else None
    if tenant_id:
        from services.runtime_limits.loader import load_runtime_limits

        lim = load_runtime_limits(tenant_id)
        limit = lim.customer_history_messages if cap is None else cap
        if clip is None:
            clip = lim.customer_message_max_chars
    else:
        limit = DEFAULT_BUDGETS.history_visible_cap if cap is None else cap
    visible: list[VisibleMessage] = []
    inbound = (current_inbound_id or "").strip()
    inbound_seen = False
    for index, raw in enumerate(raw_messages or []):
        if not isinstance(raw, dict) or not _visible(raw):
            continue
        mid = _id_of(raw, index)
        is_current = bool(inbound) and mid == inbound
        if is_current:
            inbound_seen = True
        visible.append(
            VisibleMessage(
                id=mid,
                role=_role_of(raw) or "user",
                text=_clip_text(_text_of(raw), clip),
                timestamp=str(raw.get("timestamp") or raw.get("ts") or ""),
                visible_to_customer=True,
                is_current_inbound=is_current,
            )
        )
    if inbound and not inbound_seen and (current_inbound_text or inbound):
        visible.append(
            VisibleMessage(
                id=inbound,
                role="user",
                text=_clip_text(current_inbound_text, clip),
                is_current_inbound=True,
            )
        )
        inbound_seen = True
    truncated = len(visible) > limit
    kept = visible[-limit:] if truncated else visible
    if inbound:
        marked = False
        refreshed: list[VisibleMessage] = []
        for item in kept:
            current = item.id == inbound
            if current:
                marked = True
            refreshed.append(item.model_copy(update={"is_current_inbound": current}))
        kept = refreshed
        inbound_seen = marked or inbound_seen
    return HistorySnapshot(
        messages=kept,
        high_water_mark=kept[-1].id if kept else "",
        included_inbound_ids=[inbound] if inbound and inbound_seen else [],
        truncated_to_cap=truncated,
        overflow=False,
    )
