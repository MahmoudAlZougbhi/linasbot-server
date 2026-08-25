"""WhatsApp Cloud generate/deliver. Public onboarding stays gated."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.omnichannel.gates import whatsapp_public_onboarding_live
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


async def generate_whatsapp_reply(*, tenant_id: str, payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    _live, _reason = whatsapp_public_onboarding_live()
    outcome = await run_customer_reply_v2_dm(
        tenant_id=tenant_id,
        message=str(payload.get("text_body") or payload.get("text") or ""),
        channel="whatsapp",
        provider_sender_id=str(payload.get("customer_wa_id") or ""),
    )
    if getattr(outcome, "stop", False):
        return "", None, "ai_stop"
    text = str(getattr(outcome, "reply", None) or "").strip()
    reservation = str(payload.get("credit_reservation_id") or "") or None
    return text, reservation, None if text else "empty_reply"


async def deliver_whatsapp(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant_id = str(snapshot["tenant_id"])
    connection_id = str(snapshot.get("account_id") or "")
    text = str(snapshot.get("canonical_body") or "")
    customer_wa_id = str((snapshot.get("conversation_key") or "").rsplit(":", 1)[-1])
    with whatsapp_session(require=True) as session:
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_tenant_connection(tenant_id=tenant_id, connection_id=connection_id)
        if conn is None:
            return {"http_status": 404, "error": "missing_connection", "submitted": False}
        try:
            token = repo.load_access_token(conn)
        except PermissionError:
            return {"http_status": 401, "error": "credential_unavailable", "token_expired": True, "submitted": False}
        phone_number_id = conn.phone_number_id
        session.commit()
    try:
        result = await send_text_message(
            access_token=token,
            phone_number_id=phone_number_id,
            to_wa_id=customer_wa_id,
            text=text,
        )
    except WhatsAppGraphError as exc:
        return {
            "http_status": exc.http_status or 500,
            "code": exc.code,
            "error": exc.message,
            "submitted": exc.http_status not in {None, 0},
        }
    wamid = ""
    if isinstance(result, dict):
        messages = result.get("messages") if isinstance(result.get("messages"), list) else []
        if messages and isinstance(messages[0], dict):
            wamid = str(messages[0].get("id") or "")
    return {"http_status": 200, "submitted": True, "message_id": wamid}
