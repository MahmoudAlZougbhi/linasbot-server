"""Tenant test lab. Off unless LINAS_FLAG_SANDBOX_LAB is on."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.platform.feature_flags import flag_enabled


class SandboxPostBody(BaseModel):
    platform: str = Field(min_length=2, max_length=32)
    type: str = Field(default="post", max_length=32)
    caption: str = Field(default="", max_length=2000)


class SandboxEventBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    auto_reply: bool = True


def _require_lab(request: Request) -> Any:
    if not flag_enabled("sandbox_lab"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    session = require_session(request)
    if str(session.role or "") not in {"owner", "admin", "platform_owner"}:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})
    return session


@app.post("/api/sandbox/posts")
async def sandbox_create_post(body: SandboxPostBody, request: Request) -> Any:
    session = _require_lab(request)
    from services.sandbox.lab import create_post

    return {
        "success": True,
        "post": create_post(tenant_id=session.tenant_id, platform=body.platform, kind=body.type, caption=body.caption),
    }


@app.get("/api/sandbox/posts")
async def sandbox_list_posts(request: Request) -> Any:
    session = _require_lab(request)
    from services.sandbox.lab import posts_for

    return {"success": True, "posts": posts_for(session.tenant_id)}


@app.post("/api/sandbox/posts/{post_id}/comments")
async def sandbox_comment(post_id: str, body: SandboxEventBody, request: Request) -> Any:
    session = _require_lab(request)
    from services.sandbox.lab import add_event

    try:
        event = add_event(
            tenant_id=session.tenant_id, post_id=post_id, kind="comment", text=body.text, auto_reply=body.auto_reply
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"}) from exc
    return {"success": True, "event": event}


@app.post("/api/sandbox/dms")
async def sandbox_dm(body: SandboxEventBody, request: Request) -> Any:
    session = _require_lab(request)
    from services.sandbox.lab import add_event

    event = add_event(tenant_id=session.tenant_id, post_id=None, kind="dm", text=body.text, auto_reply=body.auto_reply)
    return {"success": True, "event": event}


@app.delete("/api/sandbox")
async def sandbox_reset(request: Request) -> Any:
    session = _require_lab(request)
    from services.sandbox.lab import events_for, reset_lab

    owned = events_for(session.tenant_id)
    if owned:
        reset_lab()
    return {"success": True, "removed": len(owned)}
