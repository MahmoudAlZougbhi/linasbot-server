"""Mobile integrations + usage read APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission, require_session, user_has_permission
from modules.core import app
from services.channel_capability_disconnect import (
    clear_channel_toggles_after_disconnect,
    clear_invalid_dm_enabled_state_async,
)
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
from services.meta_app_registry import MetaRegistryError, get_meta_app_registry
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.meta_oauth import MetaOAuthError
from services.mobile_integrations_display import bindings_for_disconnect, enrich_mobile_integration_rows

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
    # Best-effort: clear stale DM/Comments when disconnected or permissions fail.
    actor = session.user_id or session.email or "channel_state_reconcile"
    for platform in supported_platforms():
        try:
            await clear_invalid_dm_enabled_state_async(
                tenant_id=session.tenant_id,
                platform=platform,
                actor=actor,
            )
        except Exception:
            pass
        try:
            await clear_invalid_comments_enabled_state_async(
                tenant_id=session.tenant_id,
                platform=platform,
                actor=actor,
            )
        except Exception:
            pass
    rows = list_tenant_integration_status(session.tenant_id)
    rows = _without_comment_capabilities(rows)
    rows = attach_channel_toggles(rows, tenant_id=session.tenant_id)
    rows = enrich_mobile_integration_rows(rows, tenant_id=session.tenant_id)
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


@app.post("/api/mobile/integrations/{platform}/disconnect")
async def mobile_disconnect_platform(platform: str, request: Request) -> Any:
    """Disconnect all active bindings for a Meta platform (no OAuth / scope changes)."""
    session = require_permission(request, "settings")
    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        raise HTTPException(status_code=404, detail="Unknown platform")

    registry = get_meta_app_registry()
    bindings = bindings_for_disconnect(session.tenant_id, platform_key, registry=registry)
    if not bindings:
        raise HTTPException(status_code=404, detail="No active connection for this platform")

    actor = session.user_id or session.email or "mobile_disconnect"
    try:
        await disconnect_meta_binding_set(bindings, actor_id=actor, registry=registry)
    except (MetaOAuthError, MetaRegistryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await clear_channel_toggles_after_disconnect(
        tenant_id=session.tenant_id,
        platform=platform_key,
        actor=actor,
    )
    rows = list_tenant_integration_status(session.tenant_id)
    rows = _without_comment_capabilities(rows)
    rows = attach_channel_toggles(rows, tenant_id=session.tenant_id)
    rows = enrich_mobile_integration_rows(rows, tenant_id=session.tenant_id)
    row = next((item for item in rows if str(item.get("platform") or "") == platform_key), None)
    return {"success": True, "platform": platform_key, "integration": row}


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
    """Usage summary for mobile Dashboard / Usage screens.

    Exposes used/limit fields the mobile UI already knows how to render.
    Does not claim a full analytics portal — credits from the file ledger only.
    """

    session = require_session(request)
    from services.credit_ai_gate import remaining_credits
    from services.entitlements_service import entitlements_store
    from services.plan_economics import PLAN_PRICES_USD, recommend_allowance

    available = remaining_credits(session.tenant_id)
    reserved = 0
    try:
        reserved = int(credit_ledger_service.get_reserved(session.tenant_id))
    except Exception:
        reserved = 0
    ent = entitlements_store.get(session.tenant_id)
    limit = int(ent.included_credits + ent.extra_credits)
    if limit <= 0 and ent.plan_id in PLAN_PRICES_USD:
        limit = int(recommend_allowance(ent.plan_id).included_credits)
    if limit <= 0:
        limit = available + reserved
    used = max(0, limit - available - reserved)
    allowance = recommend_allowance(ent.plan_id) if ent.plan_id in PLAN_PRICES_USD else None
    return {
        "success": True,
        "plan_id": ent.plan_id,
        "status": ent.status,
        "credit_balance": available,
        "credits": limit,
        "credits_limit": limit,
        "credits_used": used,
        "reserved_credits": reserved,
        "included_credits": int(ent.included_credits),
        "extra_credits": int(ent.extra_credits),
        "included_dm_replies": int(allowance.included_dm_replies) if allowance else None,
        "included_owner_messages": int(allowance.included_owner_messages) if allowance else None,
        "included_images": int(allowance.included_images) if allowance else None,
        "included_videos": int(allowance.included_videos) if allowance else None,
    }
