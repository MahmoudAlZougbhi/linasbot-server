"""Durable Live Chat operator delivery: enqueue when Redis/workers are ready.

When Redis is not required (current production), callers keep the honest
in-request provider send. Never fire-and-forget. Never guess a channel.
"""

from __future__ import annotations

from typing import Any

from services.live_chat_channel import resolve_live_chat_channel


def live_chat_durable_mode() -> str:
    """enqueue | sync | unavailable."""
    from services.omnichannel.enqueue import queue_is_durable
    from services.queues.config import redis_required

    if not redis_required():
        return "sync"
    if not queue_is_durable():
        return "unavailable"
    return "enqueue"


def queue_unavailable_result(*, channel: str) -> dict[str, Any]:
    return {
        "success": False,
        "delivered": False,
        "queued": False,
        "error": "queue_unavailable",
        "channel": channel,
        "delivery_status": "failed",
    }


def enqueue_live_chat_operator_text(
    *,
    tenant_id: str,
    channel: str,
    account_id: str,
    conversation_key: str,
    text: str,
    user_id: str,
    conversation_id: str,
    idempotency_key: str | None = None,
    control_epoch: int = 0,
) -> dict[str, Any]:
    from services.omnichannel.operator_enqueue import enqueue_operator_reply

    result = enqueue_operator_reply(
        tenant_id=tenant_id,
        channel=channel,
        surface="operator",
        account_id=account_id,
        conversation_key=conversation_key,
        text=text,
        control_epoch=control_epoch,
        idempotency_key=idempotency_key,
        live_chat={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "client_message_id": idempotency_key,
        },
    )
    result.setdefault("channel", channel)
    result.setdefault("delivery_status", "sent" if result.get("delivered") else "sending")
    return result


def try_enqueue_live_chat_whatsapp(
    *,
    tenant_id: str | None,
    user_id: str,
    canonical_user_id: str,
    conversation_id: str,
    text: str,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    """Enqueue WA Cloud when Redis is ready and a connected WABA exists.

    None means the caller must use the existing Live Chat WhatsApp adapter.
    """
    mode = live_chat_durable_mode()
    if mode == "sync":
        return None
    if resolve_live_chat_channel(user_id) != "whatsapp":
        return None
    if mode == "unavailable":
        return queue_unavailable_result(channel="whatsapp")
    tenant = str(tenant_id or "").strip()
    if not tenant:
        return None
    connection_id = _active_whatsapp_connection_id(tenant)
    if not connection_id:
        return None
    wa_id = _whatsapp_customer_wa_id(user_id, canonical_user_id)
    if not wa_id:
        return None
    return enqueue_live_chat_operator_text(
        tenant_id=tenant,
        channel="whatsapp",
        account_id=connection_id,
        conversation_key=f"{tenant}:whatsapp:{wa_id}",
        text=text,
        user_id=user_id,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
    )


def _whatsapp_customer_wa_id(user_id: str, canonical_user_id: str) -> str:
    raw = str(canonical_user_id or user_id or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]
    if raw.startswith("+"):
        raw = raw[1:]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or raw


def _active_whatsapp_connection_id(tenant_id: str) -> str | None:
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    try:
        with whatsapp_session(require=True) as session:
            repo = WhatsAppCloudRepository(session)
            conns = repo.list_tenant_connections(tenant_id, include_revoked=False)
            connected = [c for c in conns if getattr(c, "lifecycle_status", "") == "connected"]
            if not connected:
                return None
            return str(connected[0].id)
    except WhatsAppDatabaseUnavailable:
        return None
    except Exception as exc:
        print(f"⚠️ Live Chat WhatsApp enqueue: connection lookup failed: {exc}")
        return None
