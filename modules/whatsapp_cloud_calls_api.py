"""WhatsApp Call enable/disable — stores tenant intent only (no call answering yet)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from db.session import whatsapp_session
from modules.core import app
from modules.whatsapp_cloud_ops_api import _actor_id, _require_wa_manager
from services.whatsapp_cloud.entitlement import connection_status_payload
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


def _set_calls_enabled(connection_id: str, request: Request, *, enabled: bool) -> dict[str, Any]:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        conn.calls_enabled = enabled
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="calls_enabled" if enabled else "calls_disabled",
            detail={},
        )
        return {"success": True, "connection": connection_status_payload(db, conn)}


@app.post("/api/whatsapp/cloud/connections/{connection_id}/calls/enable")
async def whatsapp_enable_calls(connection_id: str, request: Request) -> Any:
    return _set_calls_enabled(connection_id, request, enabled=True)


@app.post("/api/whatsapp/cloud/connections/{connection_id}/calls/disable")
async def whatsapp_disable_calls(connection_id: str, request: Request) -> Any:
    return _set_calls_enabled(connection_id, request, enabled=False)
