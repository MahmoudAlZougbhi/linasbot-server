"""Human/operator replies use the same durable outbox as AI."""

from __future__ import annotations

import hashlib
from typing import Any

from db.session import whatsapp_session
from services.omnichannel.accept import enqueue_deliver_job
from services.omnichannel.store import persist_outbound


def enqueue_operator_reply(
    *,
    tenant_id: str,
    channel: str,
    surface: str,
    account_id: str,
    conversation_key: str,
    text: str,
    control_epoch: int = 0,
) -> dict[str, Any]:
    digest = hashlib.sha256(f"{tenant_id}:{conversation_key}:{text}".encode()).hexdigest()[:32]
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
        session.commit()
        outbox_id = row.id
    job_id = enqueue_deliver_job(
        outbox_id=outbox_id,
        tenant_id=tenant_id,
        channel=channel,
        surface=surface or "operator",
        conversation_key=conversation_key,
    )
    return {
        "success": True,
        "queued": True,
        "delivered": False,
        "outbox_id": outbox_id,
        "job_id": job_id,
        "created": created,
    }
