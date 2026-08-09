"""Scheduled content API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.schedule_service import schedule_service


class ScheduleBody(BaseModel):
    connected_account: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    content_asset: dict[str, Any]
    scheduled_at: float
    timezone: str = "UTC"
    idempotency_key: str = Field(min_length=8)


@app.get("/api/schedule/posts")
async def list_scheduled(request: Request) -> Any:
    session = require_session(request)
    posts = schedule_service.list_for_tenant(session.tenant_id)
    return {"success": True, "posts": [p.__dict__ for p in posts]}


@app.post("/api/schedule/posts")
async def create_scheduled(body: ScheduleBody, request: Request) -> Any:
    session = require_session(request)
    try:
        post = schedule_service.create(
            tenant_id=session.tenant_id,
            connected_account=body.connected_account,
            platform=body.platform,
            content_asset=body.content_asset,
            scheduled_at=body.scheduled_at,
            timezone=body.timezone,
            idempotency_key=body.idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return {"success": True, "post": post.__dict__}


@app.post("/api/schedule/posts/{post_id}/cancel")
async def cancel_scheduled(post_id: str, request: Request) -> Any:
    session = require_session(request)
    try:
        post = schedule_service.cancel(tenant_id=session.tenant_id, post_id=post_id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if post is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True, "post": post.__dict__}
