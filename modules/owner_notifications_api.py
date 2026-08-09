"""Owner notification inbox API for Linas AI mobile (auth + liveChat permission)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Query, Request

from modules.api_security import require_permission
from modules.core import app
from services.owner_alert_store import owner_alert_store
from services.owner_push_token_store import owner_push_token_store


@app.get("/api/owner-notifications")
async def list_owner_notifications(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
) -> Any:
    session = require_permission(request, "liveChat")
    items = owner_alert_store.list_alerts(
        tenant_id=session.tenant_id,
        limit=limit,
        unread_only=unread_only,
    )
    return {
        "success": True,
        "notifications": items,
        "unread_count": owner_alert_store.unread_count(tenant_id=session.tenant_id),
    }


@app.get("/api/owner-notifications/unread-count")
async def owner_notifications_unread_count(request: Request) -> Any:
    session = require_permission(request, "liveChat")
    return {
        "success": True,
        "unread_count": owner_alert_store.unread_count(tenant_id=session.tenant_id),
    }


@app.post("/api/owner-notifications/{notification_id}/read")
async def mark_owner_notification_read(notification_id: str, request: Request) -> Any:
    session = require_permission(request, "liveChat")
    row = owner_alert_store.mark_read(tenant_id=session.tenant_id, alert_id=notification_id)
    if not row:
        return {"success": False, "error": "not_found"}
    return {"success": True, "notification": row}


@app.post("/api/owner-notifications/read-all")
async def mark_all_owner_notifications_read(request: Request) -> Any:
    session = require_permission(request, "liveChat")
    count = owner_alert_store.mark_all_read(tenant_id=session.tenant_id)
    return {"success": True, "marked": count}


@app.post("/api/owner-notifications/device-token")
async def register_owner_push_device_token(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    """Scaffolding only: persist Expo/FCM token. Does not send push.

    Push delivery requires Mahmoud-approved FCM/APNs/EAS credentials.
    """
    session = require_permission(request, "liveChat")
    token = str(body.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "token_required"}
    try:
        row = owner_push_token_store.upsert(
            tenant_id=session.tenant_id,
            user_id=session.user_id or session.email or "unknown",
            token=token,
            platform=str(body.get("platform") or "").strip() or None,
            expo_project_id=str(body.get("expo_project_id") or "").strip() or None,
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "registered": True,
        "push_delivery": "disabled_pending_infra_approval",
        "token": row,
    }
