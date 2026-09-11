"""Load WhatsApp Cloud PG history when Firestore has no rows for this conversation."""

from __future__ import annotations

from typing import Any


def rows_from_wa_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(messages or []):
        direction = str(getattr(row, "direction", "") or "")
        meta = getattr(row, "meta", None)
        extra = meta if isinstance(meta, dict) else {}
        text = str(extra.get("text") or extra.get("body") or getattr(row, "content_preview", None) or "").strip()
        created = getattr(row, "created_at", None) or getattr(row, "provider_timestamp", None)
        out.append(
            {
                "id": str(getattr(row, "id", None) or f"wa:{index}"),
                "role": "user" if direction == "inbound" else "assistant",
                "text": text,
                "timestamp": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "visible_to_customer": True,
            }
        )
    return out[-50:]


def load_whatsapp_history_rows(conversation_id: str) -> list[dict[str, Any]]:
    cid = (conversation_id or "").strip()
    if len(cid) < 8:
        return []
    if cid.startswith(("web:", "comment:")) or ":tiktok:" in cid or ":instagram:" in cid or ":facebook:" in cid:
        return []
    try:
        from sqlalchemy import select

        from db.models.whatsapp_cloud import WhatsAppMessage
        from db.session import whatsapp_session

        with whatsapp_session() as session:
            rows = list(
                session.scalars(
                    select(WhatsAppMessage)
                    .where(WhatsAppMessage.conversation_id == cid)
                    .order_by(WhatsAppMessage.created_at.asc())
                    .limit(80)
                ).all()
            )
    except Exception:
        return []
    return rows_from_wa_messages(rows)
