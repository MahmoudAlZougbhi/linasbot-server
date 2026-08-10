"""Mobile integrations + usage read APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission, require_session, user_has_permission
from modules.core import app
from services.channel_capability_toggles import (
    ChannelToggleError,
    attach_channel_toggles,
    clear_invalid_comments_enabled_state_async,
    reconcile_comment_webhooks_for_platform,
    set_channel_toggle,
    supported_platforms,
)
from services.credit_ledger_service import credit_ledger_service
from services.integration_capabilities import list_tenant_integration_status

ToggleKey = Literal["dm", "comments"]


def _without_comment_capabilities(integrations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip comment_* capability-matrix jargon from mobile rows (not the toggles field)."""
    out: list[dict[str, Any]] = []
    for row in integrations:
        caps = row.get("capabilities") or {}
        if isinstance(caps, dict):
            caps = {k: v for k, v in caps.items() if not str(k).lower().startswith("comment")}
        out.append({**row, "capabilities": caps})
    return out


@app.get("/api/mobile/integrations")
async def mobile_integrations(request: Request) -> Any:
    session = require_session(request)
    # Best-effort: clear false Comments enabled when Meta comment scopes are missing.
    for platform in supported_platforms():
        try:
            await clear_invalid_comments_enabled_state_async(
                tenant_id=session.tenant_id,
                platform=platform,
                actor=session.user_id or session.email or "comments_state_reconcile",
            )
        except Exception:
            pass
    rows = list_tenant_integration_status(session.tenant_id)
    rows = _without_comment_capabilities(rows)
    rows = attach_channel_toggles(rows, tenant_id=session.tenant_id)
    return {"success": True, "integrations": rows}


@app.patch("/api/mobile/integrations/{platform}/toggles")
async def mobile_integration_toggles(
    platform: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> Any:
    """Enable/disable channel capabilities (CM Actions + comment assets). No Comments hub."""
    session = require_permission(request, "contentManagers")
    if not user_has_permission(session, "contentPublish"):
        raise HTTPException(status_code=403, detail="contentPublish permission required to apply toggles")

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        raise HTTPException(status_code=404, detail="Unknown platform")

    if "dm" in body and "comments" in body:
        raise HTTPException(status_code=400, detail="Set one toggle per request (dm or comments)")
    if "dm" in body:
        toggle: ToggleKey = "dm"
        enabled = bool(body.get("dm"))
    elif "comments" in body:
        toggle = "comments"
        enabled = bool(body.get("comments"))
    else:
        raise HTTPException(status_code=400, detail="Body must include dm or comments boolean")

    try:
        result = await set_channel_toggle(
            tenant_id=session.tenant_id,
            platform=platform_key,
            toggle=toggle,
            enabled=enabled,
            actor=session.user_id or session.email or "mobile",
        )
    except ChannelToggleError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.code,
                "message": exc.message,
                "blocker_code": exc.code,
                "reauthorize_required": exc.code == "COMMENT_SCOPES_MISSING",
            },
        )

    return {
        "success": True,
        "platform": platform_key,
        "toggles": result["toggles"],
        "comments_state": result.get("comments_state"),
        "dm_state": result.get("dm_state"),
    }


@app.post("/api/mobile/integrations/{platform}/reconcile-comments")
async def mobile_reconcile_comments(platform: str, request: Request) -> Any:
    """Reconcile comment webhooks for a connected channel (no disconnect / no revoke)."""
    session = require_permission(request, "contentManagers")
    if not user_has_permission(session, "contentPublish"):
        raise HTTPException(status_code=403, detail="contentPublish permission required")
    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        raise HTTPException(status_code=404, detail="Unknown platform")
    try:
        result = await reconcile_comment_webhooks_for_platform(
            tenant_id=session.tenant_id,
            platform=platform_key,
        )
    except ChannelToggleError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.code,
                "message": exc.message,
                "blocker_code": exc.code,
                "reauthorize_required": exc.code == "COMMENT_SCOPES_MISSING",
            },
        )
    return {
        "success": True,
        "platform": platform_key,
        "toggles": result["toggles"],
        "comments_state": result.get("comments_state"),
        "dm_state": result.get("dm_state"),
    }


@app.get("/api/mobile/usage")
async def mobile_usage(request: Request) -> Any:
    session = require_session(request)
    credit_ledger_service.ensure_period_grant(session.tenant_id)
    return {
        "success": True,
        "credit_balance": credit_ledger_service.get_balance(session.tenant_id),
    }
