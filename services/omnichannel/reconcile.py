"""Re-enqueue accepted but unfinished inbound/outbound rows."""

from __future__ import annotations

from typing import Any

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.omnichannel.accept import enqueue_deliver_job, enqueue_generate_job
from services.omnichannel.metrics import incr, set_gauge
from services.omnichannel.store import list_retryable_outbound, list_unfinished_inbound


def reconcile_omnichannel(*, older_than_seconds: float = 45.0) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    try:
        with whatsapp_session(require=True) as session:
            inbound = list_unfinished_inbound(session, older_than_seconds=older_than_seconds)
            outbound = list_retryable_outbound(session)
            inbound_ids = [
                (row.id, row.tenant_id, row.channel, row.surface, row.conversation_key, row.state) for row in inbound
            ]
            outbound_ids = [
                (row.id, row.tenant_id, row.channel, row.surface, row.conversation_key, row.state) for row in outbound
            ]
    except WhatsAppDatabaseUnavailable:
        return {"examined": 0, "actions": [], "unavailable": True}

    set_gauge("inbound_unfinished", float(len(inbound_ids)))
    set_gauge("outbound_retryable", float(len(outbound_ids)))
    for inbound_id, tenant_id, channel, surface, conversation_key, state in inbound_ids:
        try:
            if state in {"accepted", "queued", "failed", "generating"}:
                enqueue_generate_job(
                    inbound_id=inbound_id,
                    tenant_id=tenant_id,
                    channel=channel,
                    surface=surface,
                    conversation_key=conversation_key,
                )
                actions.append({"id": inbound_id, "action": "requeue_generate"})
            elif state in {"reply_ready", "rate_limited", "sending", "reconciliation_required"}:
                incr("reconcile_inbound_waiting_outbox")
        except Exception as exc:
            actions.append({"id": inbound_id, "action": "enqueue_failed", "error": type(exc).__name__})
    for outbox_id, tenant_id, channel, surface, conversation_key, state in outbound_ids:
        try:
            enqueue_deliver_job(
                outbox_id=outbox_id,
                tenant_id=tenant_id,
                channel=channel,
                surface=surface,
                conversation_key=conversation_key,
            )
            actions.append({"id": outbox_id, "action": "requeue_deliver", "state": state})
        except Exception as exc:
            actions.append({"id": outbox_id, "action": "enqueue_failed", "error": type(exc).__name__})
    incr("reconcile_runs")
    return {"examined": len(inbound_ids) + len(outbound_ids), "actions": actions}
