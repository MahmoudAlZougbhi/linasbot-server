"""Load Website Chat history when Firestore has no rows for this conversation."""

from __future__ import annotations

from typing import Any


def session_id_from_conversation(conversation_id: str) -> str:
    cid = (conversation_id or "").strip()
    if cid.startswith("web:"):
        parts = cid.split(":", 2)
        if len(parts) == 3 and parts[2].strip():
            return parts[2].strip()
    return cid


def rows_from_web_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(messages or []):
        role = str(getattr(row, "role", "") or "").strip().lower()
        created = getattr(row, "created_at", None)
        out.append(
            {
                "id": str(getattr(row, "id", None) or f"web:{index}"),
                "role": "user" if role in {"user", "customer", "visitor"} else "assistant",
                "text": str(getattr(row, "content", None) or getattr(row, "text", None) or "").strip(),
                "timestamp": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "visible_to_customer": True,
            }
        )
    return out[-50:]


def load_web_history_rows(conversation_id: str) -> list[dict[str, Any]]:
    sid = session_id_from_conversation(conversation_id)
    if len(sid) < 8:
        return []
    try:
        from services.web_chat.store import web_chat_store

        visitor = web_chat_store.get_visitor(sid)
    except Exception:
        return []
    if visitor is None:
        return []
    return rows_from_web_messages(list(getattr(visitor, "messages", None) or []))
