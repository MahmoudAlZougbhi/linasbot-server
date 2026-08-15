"""Wire outbound product sends to reply-to map (0 credits on inbound reply)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PENDING_KEY = "_pending_product_outbound"


def _normalize_channel(channel: str | None) -> str:
    ch = str(channel or "whatsapp").strip().lower()
    if "instagram" in ch:
        return "instagram_dm"
    if "facebook" in ch or ch in {"messenger", "page"}:
        return "facebook_dm"
    if ch in {"web_chat", "webchat", "web"}:
        return "web_chat"
    return ch or "whatsapp"


def set_pending_product_outbound(
    user_data: dict[str, Any],
    *,
    product_id: str,
    source: str = "ai_reply",
) -> None:
    pid = str(product_id or "").strip()
    if not pid:
        return
    user_data[PENDING_KEY] = {"product_id": pid, "source": source}


def clear_pending_product_outbound(user_data: dict[str, Any]) -> None:
    user_data.pop(PENDING_KEY, None)


def maybe_record_product_outbound(
    user_data: dict[str, Any],
    *,
    provider_message_id: str,
) -> bool:
    """Record sent product message after successful outbound delivery."""
    pending = user_data.pop(PENDING_KEY, None)
    message_id = str(provider_message_id or "").strip()
    if not pending or not message_id:
        return False
    product_id = str(pending.get("product_id") or "").strip()
    if not product_id:
        return False
    tenant_id = str(user_data.get("tenant_id") or user_data.get("tenantId") or "").strip()
    conversation_id = str(
        user_data.get("conversation_id")
        or user_data.get("active_conversation_id")
        or user_data.get("current_conversation_id")
        or ""
    ).strip()
    channel = _normalize_channel(user_data.get("channel") or user_data.get("platform"))
    if not tenant_id or not conversation_id:
        logger.debug(
            "product_outbound_skip_missing_context tenant=%s conversation=%s",
            tenant_id,
            conversation_id,
        )
        return False
    try:
        from db.session import whatsapp_session
        from services.products.reply_to_map import record_sent_product_message

        with whatsapp_session(require=True) as session:
            record_sent_product_message(
                session,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                channel=channel,
                sent_message_id=message_id,
                product_id=product_id,
            )
            session.commit()
        return True
    except Exception:
        logger.exception(
            "product_outbound_record_failed tenant=%s product=%s msg=%s",
            tenant_id,
            product_id,
            message_id,
        )
        return False


def record_product_outbound_direct(
    *,
    tenant_id: str,
    conversation_id: str,
    channel: str,
    sent_message_id: str,
    product_id: str,
) -> None:
    """Direct record for channels that don't use user_data (Meta guarded send, live chat)."""
    message_id = str(sent_message_id or "").strip()
    if not message_id or not product_id:
        return
    from db.session import whatsapp_session
    from services.products.reply_to_map import record_sent_product_message

    with whatsapp_session(require=True) as session:
        record_sent_product_message(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel=_normalize_channel(channel),
            sent_message_id=message_id,
            product_id=product_id,
        )
        session.commit()
