"""Authenticated Smart Follow-Up APIs (tenant-scoped, server-authoritative)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import is_platform_owner, require_permission, require_session, user_has_permission
from modules.core import app
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility, tenant_has_whatsapp_pilot
from services.whatsapp_cloud.repository import WhatsAppCloudRepository
from services.whatsapp_cloud.smart_followup.analytics import (
    build_smart_followup_analytics,
    resolve_analytics_window,
)
from services.whatsapp_cloud.smart_followup.constants import OPERATION_TYPE
from services.whatsapp_cloud.smart_followup.generation import generate_followup_text, preview_prompt_for_goal
from services.whatsapp_cloud.smart_followup.repository import SmartFollowUpRepository
from services.whatsapp_cloud.smart_followup.settings_service import (
    SmartFollowUpSettingsError,
    get_or_create_settings,
    update_settings,
)


def _actor_id(session: Any) -> str:
    return str(session.user_id or session.email or "unknown")


def _require_manager(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    if not user_has_permission(session, "contentPublish") and not is_platform_owner(session):
        role = (session.role or "").strip().lower()
        if role not in {"owner", "admin", "platform_owner"}:
            raise HTTPException(status_code=403, detail="owner_or_admin_required")
    return session


def _connection_blockers(db: Any, tenant_id: str) -> dict[str, Any]:
    repo = WhatsAppCloudRepository(db)
    connections = [c for c in repo.list_tenant_connections(tenant_id) if c.lifecycle_status != "revoked"]
    primary = connections[0] if connections else None
    connected = bool(primary and primary.lifecycle_status == "connected")
    ai_eligible = False
    ai_reason = None
    if primary is not None:
        ai_eligible, ai_reason = evaluate_ai_eligibility(db, primary)
    pilot = tenant_has_whatsapp_pilot(db, tenant_id)
    return {
        "whatsapp_connected": connected,
        "lifecycle_status": primary.lifecycle_status if primary else "disconnected",
        "ai_eligible": ai_eligible,
        "ai_blocker": None if ai_eligible else ai_reason,
        "pilot_entitled": pilot,
        "route_integrations_when_disconnected": not connected,
    }


@app.get("/api/whatsapp/smart-followup/settings")
async def smart_followup_get_settings(request: Request) -> Any:
    session = require_session(request)
    try:
        with whatsapp_session() as db:
            payload = get_or_create_settings(db, session.tenant_id)
            payload["blockers"] = _connection_blockers(db, session.tenant_id)
            return payload
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "WHATSAPP_DB_UNAVAILABLE",
                "message": "WhatsApp Cloud database is not configured",
            },
        )


@app.put("/api/whatsapp/smart-followup/settings")
async def smart_followup_put_settings(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_manager(request)
    expected = body.get("settings_version")
    try:
        expected_version = int(expected) if expected is not None else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_settings_version") from exc
    try:
        with whatsapp_session() as db:
            payload = update_settings(
                db,
                tenant_id=session.tenant_id,
                actor_user_id=_actor_id(session),
                payload=body,
                expected_version=expected_version,
            )
            payload["blockers"] = _connection_blockers(db, session.tenant_id)
            return payload
    except SmartFollowUpSettingsError as exc:
        status = 409 if exc.code == "version_conflict" else 400
        return JSONResponse(
            status_code=status,
            content={"success": False, "error": exc.code, "message": exc.message},
        )
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "WHATSAPP_DB_UNAVAILABLE",
                "message": "WhatsApp Cloud database is not configured",
            },
        )


@app.get("/api/whatsapp/smart-followup/analytics")
async def smart_followup_analytics(
    request: Request,
    period: str = "7d",
    timezone: str = "UTC",
    start: str | None = None,
    end: str | None = None,
) -> Any:
    session = require_session(request)
    try:
        start_dt, end_dt, tz_name = resolve_analytics_window(
            period=period,
            timezone_name=timezone,
            start_iso=start,
            end_iso=end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        with whatsapp_session() as db:
            return build_smart_followup_analytics(
                db,
                tenant_id=session.tenant_id,
                start=start_dt,
                end=end_dt,
                timezone_name=tz_name,
            )
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "availability": "error",
                "error": "WHATSAPP_DB_UNAVAILABLE",
                "message": "WhatsApp Cloud database is not configured",
            },
        )


@app.post("/api/whatsapp/smart-followup/preview")
async def smart_followup_preview(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    """Safe preview — never sends WhatsApp; may consume AI credits via Customer Reply V2."""
    session = _require_manager(request)
    goal = str(body.get("goal") or "gentle_check_in").strip()
    disclose = {
        "sends_whatsapp": False,
        "uses_credits": True,
        "disclosure": "Preview uses the canonical AI credit engine and never sends a WhatsApp message.",
        **preview_prompt_for_goal(goal),
    }
    reservation_id: str | None = None
    try:
        with whatsapp_session() as db:
            blockers = _connection_blockers(db, session.tenant_id)
            if not blockers.get("whatsapp_connected"):
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "whatsapp_disconnected",
                        "message": "Connect WhatsApp in Integrations before previewing.",
                        "blockers": blockers,
                        **disclose,
                    },
                )
            repo = WhatsAppCloudRepository(db)
            connections = [
                c for c in repo.list_tenant_connections(session.tenant_id) if c.lifecycle_status == "connected"
            ]
            conn = connections[0]
            from services.credit_ledger_service import credit_ledger_service

            try:
                reservation_id = credit_ledger_service.reserve(
                    tenant_id=session.tenant_id,
                    user_id=_actor_id(session),
                    credits=1,
                    operation_type=OPERATION_TYPE,
                    request_id=f"sfu-preview:{session.tenant_id}:{goal}:{_actor_id(session)}",
                )
            except PermissionError:
                return JSONResponse(
                    status_code=402,
                    content={
                        "success": False,
                        "error": "insufficient_credits",
                        "message": "Insufficient AI credits for preview",
                        **disclose,
                    },
                )
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE", **disclose},
        )

    try:
        text = await generate_followup_text(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            conversation_id=f"preview:{session.tenant_id}",
            customer_wa_id="preview_customer",
            goal=goal,
        )
    except Exception as exc:
        if reservation_id:
            try:
                from services.credit_ledger_service import credit_ledger_service

                credit_ledger_service.release(tenant_id=session.tenant_id, reservation_id=reservation_id)
            except Exception:
                pass
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "preview_generation_failed",
                "message": type(exc).__name__,
                **disclose,
            },
        )

    try:
        from services.credit_ledger_service import credit_ledger_service

        if reservation_id:
            credit_ledger_service.capture(
                tenant_id=session.tenant_id,
                reservation_id=reservation_id,
                provider_cost_usd=None,
                model_provider="whatsapp_cloud",
            )
    except Exception:
        pass

    with whatsapp_session() as db:
        SmartFollowUpRepository(db).record_event(
            tenant_id=session.tenant_id,
            event_type="preview_generated",
            detail={"goal": goal, "actor_user_id": _actor_id(session)},
        )

    return {
        "success": True,
        "preview_text": text,
        "live_customer_result": False,
        **disclose,
    }
