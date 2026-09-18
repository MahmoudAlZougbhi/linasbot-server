"""Platform owner control center HTTP facade."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.owner_portal.overview import analytics, list_subscribers
from services.owner_portal.users import update_platform_user


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
    try:
        user = update_platform_user(
            actor_user_id=session.user_id,
            user_id=user_id,
            status=body.status,
            role=body.role,
            password=body.password,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "user": user}
