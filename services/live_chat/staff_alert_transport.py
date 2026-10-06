"""Staff WhatsApp alerts leave only through that tenant's connection."""

from __future__ import annotations

from typing import Any

import httpx


async def deliver_staff_whatsapp(
    *,
    tenant_id: str,
    numbers: list[str],
    template_name: str,
    template_language: str,
    parameters: dict[str, str],
) -> dict[str, Any]:
    del parameters
    tid = str(tenant_id or "").strip()
    name = str(template_name or "").strip()
    language = str(template_language or "").strip()
    if not tid or not numbers or not name or not language:
        return {"success": False, "error": "tenant_staff_alert_unavailable", "sent_count": 0}

    from db.session import whatsapp_session
    from services.integrations.whatsapp.repository import WhatsAppCloudRepository

    with whatsapp_session(require=True) as session:
        repo = WhatsAppCloudRepository(session)
        connection = next(
            (
                conn
                for conn in repo.list_tenant_connections(tid, include_revoked=False)
                if conn.lifecycle_status == "connected" and str(conn.phone_number_id or "").strip()
            ),
            None,
        )
        if connection is None:
            return {"success": False, "error": "tenant_delivery_unavailable", "sent_count": 0}
        try:
            token = repo.load_access_token(connection)
        except Exception:
            return {"success": False, "error": "tenant_delivery_unavailable", "sent_count": 0}
        phone_number_id = str(connection.phone_number_id)

    sent = 0
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for number in numbers:
            body = {
                "messaging_product": "whatsapp",
                "to": number.lstrip("+"),
                "type": "template",
                "template": {"name": name, "language": {"code": language}},
            }
            response = await client.post(url, headers=headers, json=body)
            if response.status_code < 400:
                sent += 1
    if sent == 0:
        return {"success": False, "error": "tenant_template_rejected", "sent_count": 0}
    return {"success": True, "sent_count": sent, "total_numbers": len(numbers)}
