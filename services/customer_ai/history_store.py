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
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        role = str(row.get("role") or row.get("sender_role") or "user")
        out.append(
            {
                "id": str(row.get("id") or row.get("message_id") or f"hist:{index}"),
                "role": role,
                "text": str(row.get("text") or row.get("content") or ""),
                "timestamp": str(row.get("timestamp") or ""),
                "visible_to_customer": row.get("visible_to_customer", meta.get("visible_to_customer")),
                "private_staff_note": row.get("private_staff_note") or meta.get("private_staff_note"),
                "internal": row.get("internal") or meta.get("internal"),
                "unsent": row.get("unsent") or meta.get("unsent"),
                "kind": row.get("kind") or meta.get("kind"),
            }
        )
    return out


def _channel_name(channel: str) -> str:
    return (channel or "").strip().lower()


def _looks_whatsapp(conversation_id: str, channel: str) -> bool:
    name = _channel_name(channel)
    return name in {"whatsapp", "whatsapp_cloud", "wa"} or name.startswith("whatsapp")


def _looks_web(conversation_id: str, channel: str) -> bool:
    return (conversation_id or "").startswith("web:") or _channel_name(channel) in {"web", "web_chat", "website"}


def _looks_tiktok(conversation_id: str, channel: str) -> bool:
    cid = conversation_id or ""
    name = _channel_name(channel)
    return name.startswith("tiktok") or ":tiktok:" in cid


def _looks_meta(conversation_id: str, channel: str) -> bool:
    """Instagram/Facebook threads reuse conversation-store history. No new PG table."""
    cid = (conversation_id or "").lower()
    name = _channel_name(channel)
    return (
        name.startswith("instagram")
        or name.startswith("facebook")
        or name in {"meta", "ig", "fb"}
        or cid.startswith("ig-")
        or cid.startswith("fb-")
    )


async def load_history_snapshot(
    *,
    user_id: str,
    conversation_id: str,
    current_inbound_id: str = "",
    current_inbound_text: str = "",
    injected: list[dict[str, Any]] | None = None,
    tenant_id: str = "",
    channel: str = "",
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
    if not rows and _looks_whatsapp(conversation_id, channel):
        from services.customer_ai.history_whatsapp import load_whatsapp_history_rows

        rows = load_whatsapp_history_rows(conversation_id)
    if not rows and _looks_web(conversation_id, channel):
        from services.customer_ai.history_web import load_web_history_rows

        rows = load_web_history_rows(conversation_id)
    if not rows and _looks_tiktok(conversation_id, channel):
        from services.customer_ai.history_tiktok import load_tiktok_history_rows

        rows = load_tiktok_history_rows(conversation_id)
    if not rows and tenant_id and _looks_meta(conversation_id, channel):
        from services.customer_ai.conversation_history import load_stored_history_rows

        rows = load_stored_history_rows(tenant_id, conversation_id)
    if not rows and tenant_id:
        from services.customer_ai.conversation_history import load_stored_history_rows

        rows = load_stored_history_rows(tenant_id, conversation_id)
    return build_history_snapshot(
        _as_raw(rows),
        current_inbound_id=current_inbound_id,
        current_inbound_text=current_inbound_text,
    )
