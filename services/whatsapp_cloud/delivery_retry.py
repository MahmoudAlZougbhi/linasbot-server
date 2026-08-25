"""Retry WhatsApp outbound intents that failed with retryable Graph errors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models.whatsapp_cloud import WhatsAppOutboundIntent
from db.session import whatsapp_session
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


async def send_canonical_intent(intent_id: str) -> dict[str, Any]:
    with whatsapp_session(require=True) as session:
        intent = session.get(WhatsAppOutboundIntent, intent_id)
        if intent is None:
            return {"ok": False, "reason": "missing_intent"}
        if intent.dispatch_state == "sent":
            return {"ok": True, "skipped": True, "reason": "already_sent"}
        text = str(getattr(intent, "canonical_text", "") or "")
        if not text:
            return {"ok": False, "reason": "missing_canonical_text"}
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_tenant_connection(tenant_id=intent.tenant_id, connection_id=intent.connection_id)
        if conn is None:
            return {"ok": False, "reason": "missing_connection"}
        conv = repo.get_tenant_conversation(tenant_id=intent.tenant_id, conversation_id=intent.conversation_id)
        if conv is None:
            return {"ok": False, "reason": "missing_conversation"}
        token = repo.load_access_token(conn)
        to_wa_id = conv.customer_wa_id
        phone_number_id = conn.phone_number_id
        intent.dispatch_state = "sending"
        intent.attempt_count = int(getattr(intent, "attempt_count", 0) or 0) + 1
        session.commit()
    try:
        result = await send_text_message(
            access_token=token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            text=text,
        )
    except WhatsAppGraphError as exc:
        ambiguous = exc.retryable and exc.http_status in {None, 408, 504}
        with whatsapp_session(require=True) as session:
            intent = session.get(WhatsAppOutboundIntent, intent_id)
            if intent is not None:
                intent.dispatch_state = "reconciliation_required" if ambiguous else "failed"
                intent.error_code = exc.code
                intent.error_detail = (exc.message or "")[:255]
                session.commit()
        return {"ok": False, "retryable": exc.retryable and not ambiguous, "code": exc.code}
    wamid = ""
    if isinstance(result, dict):
        messages = result.get("messages") if isinstance(result.get("messages"), list) else []
        if messages and isinstance(messages[0], dict):
            wamid = str(messages[0].get("id") or "")
    with whatsapp_session(require=True) as session:
        intent = session.get(WhatsAppOutboundIntent, intent_id)
        if intent is not None:
            intent.dispatch_state = "sent"
            intent.provider_wamid = wamid or intent.provider_wamid
            session.commit()
    return {"ok": True, "wamid": wamid}


async def retry_pending_outbound_intents(*, tenant_id: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    with whatsapp_session(require=True) as session:
        stmt = select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.dispatch_state.in_(("failed", "pending")))
        if tenant_id:
            stmt = stmt.where(WhatsAppOutboundIntent.tenant_id == tenant_id)
        rows = list(session.scalars(stmt).all())
        ids = []
        for row in rows:
            nxt = getattr(row, "next_retry_at", None)
            if nxt is not None and nxt > now:
                continue
            ids.append(row.id)
    results = []
    for intent_id in ids:
        results.append(await send_canonical_intent(intent_id))
    return {"ok": True, "attempted": len(ids), "results": results}
