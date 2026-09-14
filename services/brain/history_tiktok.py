"""Load TikTok Business PG history when Firestore has no rows for this conversation."""

from __future__ import annotations

from typing import Any


def provider_conversation_id(conversation_id: str) -> str:
    cid = (conversation_id or "").strip()
    if ":tiktok:" in cid:
        return cid.rsplit(":", 1)[-1].strip()
    return cid


def rows_from_tt_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(messages or []):
        direction = str(getattr(row, "direction", "") or "")
        created = getattr(row, "created_at", None)
        out.append(
            {
                "id": str(getattr(row, "provider_message_id", None) or getattr(row, "id", None) or f"tt:{index}"),
                "role": "user" if direction == "inbound" else "assistant",
                "text": str(getattr(row, "text", None) or "").strip(),
                "timestamp": created.isoformat()
                if created is not None and hasattr(created, "isoformat")
                else str(created or ""),
                "visible_to_customer": True,
            }
        )
    return out[-50:]


def load_tiktok_history_rows(conversation_id: str) -> list[dict[str, Any]]:
    cid = provider_conversation_id(conversation_id)
    if len(cid) < 8 or cid.startswith(("web:", "comment:")):
        return []
    if ":instagram:" in conversation_id or ":facebook:" in conversation_id:
        return []
    try:
        from sqlalchemy import select

        from db.models.tiktok_content import TikTokConversation, TikTokMessage
        from db.session import whatsapp_session

        with whatsapp_session() as session:
            conv = session.scalar(select(TikTokConversation).where(TikTokConversation.conversation_id == cid).limit(1))
            if conv is None:
                return []
            rows = list(
                session.scalars(
                    select(TikTokMessage)
                    .where(TikTokMessage.conversation_row_id == conv.id)
                    .order_by(TikTokMessage.created_at.asc())
                    .limit(80)
                ).all()
            )
    except Exception:
        return []
    return rows_from_tt_messages(rows)
