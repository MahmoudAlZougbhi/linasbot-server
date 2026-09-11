"""Platform owner control center API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.dashboard_session_service import session_service
from services.owner_portal_service import analytics, list_subscribers
from services.platform_owner_service import platform_owner_service
from services.tenant_custom_roles import tenant_custom_roles
from services.user_service import user_service


class PlatformUserUpdateBody(BaseModel):
    status: str | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


@app.get("/api/platform/analytics")
async def platform_analytics(
    request: Request,
    range_key: str = Query(default="last_7_days"),
) -> Any:
    require_platform_owner(request)
    try:
        return {"success": True, "analytics": analytics(range_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/platform/users")
async def platform_users(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "subscribers": list_subscribers()}


@app.patch("/api/platform/users/{user_id}")
async def platform_update_user(user_id: str, body: PlatformUserUpdateBody, request: Request) -> Any:
    session = require_platform_owner(request)
    target = user_service.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target.get("role") or "").lower() == "platform_owner":
        raise HTTPException(status_code=403, detail="Platform-owner accounts are CLI-managed")
    updates: dict[str, Any] = {}
    if body.status is not None:
        status = body.status.strip().lower()
        if status not in {"active", "blocked"}:
            raise HTTPException(status_code=400, detail="Status must be active or blocked")
        updates["status"] = status
    if body.role is not None:
        tenant_id = str(target.get("tenantId") or "").strip()
        updates["role"] = body.role
        updates["_custom_role_ids"] = tenant_custom_roles.role_ids(tenant_id)
    if body.password is not None:
        updates["password"] = body.password
    if not updates:
        raise HTTPException(status_code=400, detail="No supported changes supplied")
    try:
        user = user_service.update_user(user_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_service.revoke_all_for_user(user_id)
    platform_owner_service.log_action(
        actor_user_id=session.user_id,
        action="update_user",
        tenant_id=str(target.get("tenantId") or ""),
        details={"user_id": user_id, "fields": sorted(k for k in updates if not k.startswith("_"))},
    )
    return {"success": True, "user": user}
