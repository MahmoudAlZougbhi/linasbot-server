"""Human/operator replies use the same durable outbox as AI."""

from __future__ import annotations

import hashlib
from typing import Any

from db.session import whatsapp_session
from services.omnichannel.accept import enqueue_deliver_job
from services.omnichannel.store import persist_outbound

_IN_FLIGHT = frozenset({"queued", "sending", "rate_limited", "reconciliation_required"})
_RETRYABLE = frozenset({"dead_letter", "needs_owner_action", "failed"})


def enqueue_operator_reply(
    *,
    tenant_id: str,
    channel: str,
    surface: str,
    account_id: str,
    conversation_key: str,
    text: str,
    control_epoch: int = 0,
    idempotency_key: str | None = None,
    live_chat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_key = str(idempotency_key or "").strip() or f"{tenant_id}:{conversation_key}:{text}"
    digest = hashlib.sha256(f"op-key:{raw_key}".encode()).hexdigest()[:32]
    extra = _live_chat_payload(live_chat)
    if extra:
        extra["tenant_id"] = tenant_id
    with whatsapp_session(require=True) as session:
        row, created = persist_outbound(
            session,
            tenant_id=tenant_id,
            channel=channel,
            surface=surface or "operator",
            account_id=account_id,
            conversation_key=conversation_key,
            inbound_event_id=None,
            canonical_body=text,
            idempotency_key=f"op:{digest}",
            control_epoch=control_epoch,
            source="operator",
        )
        outbox_id = row.id
        state = str(row.state or "")
        if not created and state == "delivered":
            session.commit()
            return {
                "success": True,
                "queued": False,
                "delivered": True,
                "duplicate": True,
                "outbox_id": outbox_id,
                "delivery_status": "sent",
            }
        if not created and state in _IN_FLIGHT:
            session.commit()
            return {
                "success": True,
                "queued": True,
                "delivered": False,
                "duplicate": True,
                "outbox_id": outbox_id,
                "delivery_status": "sending",
            }
        retry = False
        if not created and state in _RETRYABLE:
            row.state = "queued"
            row.last_error = None
            retry = True
        session.commit()
    job_id = enqueue_deliver_job(
        outbox_id=outbox_id,
        tenant_id=tenant_id,
        channel=channel,
        surface=surface or "operator",
        conversation_key=conversation_key,
        extra_payload=extra,
        job_idempotency_key=f"omni_del:{outbox_id}:retry:{digest}" if retry else None,
    )
    return {
        "success": True,
        "queued": True,
        "delivered": False,
        "outbox_id": outbox_id,
        "job_id": job_id,
        "created": created,
        "delivery_status": "sending",
    }


def _live_chat_payload(live_chat: dict[str, Any] | None) -> dict[str, Any]:
    if not live_chat:
        return {}
    mapped = {
        "live_chat_user_id": live_chat.get("user_id"),
        "live_chat_conversation_id": live_chat.get("conversation_id"),
        "live_chat_client_message_id": live_chat.get("client_message_id"),
    }
    return {key: value for key, value in mapped.items() if value}
