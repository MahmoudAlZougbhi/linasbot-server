"""Owner replay and backlog visibility for omnichannel delivery."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.api_security import require_platform_owner
from modules.core import app


@app.get("/api/omnichannel/backlog")
async def omnichannel_backlog(request: Request) -> Any:
    require_platform_owner(request)
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    from services.omnichannel.metrics import snapshot
    from services.omnichannel.store import backlog_snapshot

    counts: dict[str, Any] = {"unavailable": True}
    try:
        with whatsapp_session(require=True) as session:
            counts = backlog_snapshot(session)
    except WhatsAppDatabaseUnavailable:
        counts = {"unavailable": True}
    return {"success": True, "metrics": snapshot(), "backlog": counts}


@app.post("/api/omnichannel/replay")
async def omnichannel_replay(request: Request) -> Any:
    require_platform_owner(request)
    body = await request.json()
    if not isinstance(body, dict):
        return {"success": False, "error": "invalid_payload"}
    from db.models.omnichannel import OmnichannelOutboundOutbox
    from db.session import whatsapp_session
    from services.omnichannel.accept import enqueue_deliver_job
    from services.omnichannel.dlq import replay_delivery_only

    try:
        replay_delivery_only({**body, "mode": str(body.get("mode") or "delivery_only")})
    except PermissionError as exc:
        return {"success": False, "error": str(exc)}
    outbox_id = str(body.get("outbox_id") or "").strip()
    if not outbox_id:
        return {"success": False, "error": "outbox_id_required"}
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            return {"success": False, "error": "outbox_missing"}
        if row.regenerated:
            return {"success": False, "error": "canonical_body_must_not_regenerate"}
        tenant_id = row.tenant_id
        channel = row.channel
        surface = row.surface
        conversation_key = row.conversation_key
    job_id = enqueue_deliver_job(
        outbox_id=outbox_id,
        tenant_id=tenant_id,
        channel=channel,
        surface=surface,
        conversation_key=conversation_key,
    )
    return {"success": True, "job_id": job_id, "mode": "delivery_only"}
