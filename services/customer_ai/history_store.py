"""Load the latest 50 visible messages. Do not apply the 12h Meta window here."""

from __future__ import annotations

from typing import Any

from services.customer_ai.history import build_history_snapshot
from services.customer_ai.contracts.turn import HistorySnapshot


def _as_raw(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": str(row.get("id") or row.get("message_id") or f"hist:{index}"),
                "role": str(row.get("role") or "user"),
                "text": str(row.get("text") or row.get("content") or ""),
                "timestamp": str(row.get("timestamp") or ""),
            }
        )
    return out


async def load_history_snapshot(
    *,
    user_id: str,
    conversation_id: str,
    current_inbound_id: str = "",
    current_inbound_text: str = "",
    injected: list[dict[str, Any]] | None = None,
) -> HistorySnapshot:
    if injected is not None:
        return build_history_snapshot(
            injected,
            current_inbound_id=current_inbound_id,
            current_inbound_text=current_inbound_text,
        )
    if not user_id or not conversation_id:
        return build_history_snapshot(
            [],
            current_inbound_id=current_inbound_id,
            current_inbound_text=current_inbound_text,
        )
    try:
        from utils.utils_context import get_conversation_history_from_firestore

        rows = await get_conversation_history_from_firestore(
            user_id,
            conversation_id,
            max_messages=0,
            window_hours=0,
            include_metadata=True,
        )
    except Exception:
        rows = []
    return build_history_snapshot(
        _as_raw(rows),
        current_inbound_id=current_inbound_id,
        current_inbound_text=current_inbound_text,
    )
