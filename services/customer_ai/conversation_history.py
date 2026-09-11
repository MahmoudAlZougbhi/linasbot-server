"""Rolling latest-50 visible history on the conversation store.

Used only when Firestore / WhatsApp / web / TikTok stores miss. This is not a
new billing table and does not invent Instagram/Facebook PG history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.reply import TurnResult
from services.customer_ai.contracts.turn import ConversationState, CustomerTurn
from services.customer_ai.conversation_store import load_conversation, save_conversation

_VISIBLE_DESTINATIONS = frozenset({"dm", "comment", "web_chat", ""})


def load_stored_history_rows(tenant_id: str, conversation_id: str) -> list[dict[str, Any]]:
    raw = load_conversation(tenant_id, conversation_id)
    if raw is None:
        return []
    rows = raw.get("history") or []
    return [row for row in rows if isinstance(row, dict)][-DEFAULT_BUDGETS.history_visible_cap :]


def append_visible_history(
    tenant_id: str,
    conversation_id: str,
    rows: list[dict[str, Any]],
) -> None:
    if not tenant_id.strip() or not conversation_id.strip() or not rows:
        return
    raw = load_conversation(tenant_id, conversation_id) or {}
    merged = [row for row in (raw.get("history") or []) if isinstance(row, dict)]
    seen = {str(row.get("id") or "") for row in merged if row.get("id")}
    now = datetime.now(UTC).isoformat()
    for row in rows:
        text = str(row.get("text") or "").strip()
        rid = str(row.get("id") or "").strip()
        if not text:
            continue
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        merged.append(
            {
                "id": rid or f"hist:{len(merged)}",
                "role": str(row.get("role") or "user"),
                "text": text,
                "timestamp": str(row.get("timestamp") or now),
                "visible_to_customer": True,
            }
        )
    try:
        state = ConversationState.model_validate(raw.get("state") or {})
    except Exception:
        state = ConversationState()
    save_conversation(
        tenant_id,
        conversation_id,
        state,
        list(raw.get("pending") or []),
        history=merged[-DEFAULT_BUDGETS.history_visible_cap :],
    )


def record_turn_history(
    turn: CustomerTurn,
    *,
    inbound_id: str = "",
    inbound_text: str = "",
    result: TurnResult | None = None,
    comment_surface: bool = False,
) -> None:
    rows: list[dict[str, Any]] = []
    inbound = (inbound_text or "").strip()
    if not inbound:
        kinds = [str(item) for item in (getattr(turn.media, "attachment_types", None) or []) if str(item).strip()]
        if kinds:
            inbound = f"[Customer sent a {kinds[0]}]"
    if inbound:
        rows.append(
            {
                "id": (inbound_id or "").strip() or f"in:{turn.conversation_id}:{len(inbound)}",
                "role": "user",
                "text": inbound,
            }
        )
    if result is not None:
        for item in result.envelope.messages:
            text = (item.text or "").strip()
            dest = item.destination or ""
            if not text or dest not in _VISIBLE_DESTINATIONS:
                continue
            if comment_surface and dest == "dm":
                continue
            rows.append(
                {
                    "id": item.idempotency_key or f"out:{dest}:{abs(hash(text))}",
                    "role": "assistant",
                    "text": text,
                }
            )
    append_visible_history(turn.tenant_id, turn.conversation_id, rows)
