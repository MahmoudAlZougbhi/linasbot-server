"""
AI Setup control-plane API.

Draft CRUD with ETag concurrency and publish/unpublish (hard-403 when disabled).
All storage operations use the authenticated session tenant — never a client-supplied tenant id.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission, require_session
from modules.core import app
from services.cm.constants import CM_SECTIONS, PUBLISH_DISABLED_MESSAGE, cm_faq_canonical, cm_runtime_mode
from services.cm.provenance_headers import sanitize_section_payload
from services.cm.publish import PublishBlockedError, publish_draft, publish_faq_only
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled, publish_status
from services.cm.storage import ConflictError, UnknownSectionError, get_draft, put_draft
from services.dashboard_session_service import SessionRecord
from services.search_metadata.errors import (
    METADATA_PREPARATION_CODE,
    METADATA_PREPARATION_MESSAGE,
    MetadataPreparationError,
)


def _publish_disabled_response(message: str | None = None) -> JSONResponse:
    text = message or PUBLISH_DISABLED_MESSAGE
    return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "error": "PUBLISH_DISABLED",
            "message": text,
            "detail": text,
        },
    )


def _envelope_dict(envelope: Any) -> dict[str, Any]:
    if hasattr(envelope, "model_dump"):
        dumped = envelope.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    return dict(envelope)


def _owner_sanitize_envelope(data: dict[str, Any], section: str) -> dict[str, Any]:
    """Hide remigrate provenance markers from owner-facing draft responses."""
    out = dict(data)
    payload = out.get("payload")
    if isinstance(payload, dict):
        out["payload"] = sanitize_section_payload(section, payload)
    return out


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


@app.get("/api/cm/meta")
async def cm_meta(request: Request) -> Any:
    session = require_session(request)
    status = publish_status()
    tenant_id = _session_tenant(session)
    from services.cm.constants import (
        tenant_allows_legacy_bridge,
        tenant_has_published_cm,
        tenant_uses_cm_runtime,
    )

    if tenant_uses_cm_runtime(tenant_id):
        tenant_runtime = "published"
    elif tenant_allows_legacy_bridge(tenant_id):
        tenant_runtime = "legacy_bridge"
    else:
        tenant_runtime = "unpublished"

    return {
        "success": True,
        "tenant_id": tenant_id,
        "sections": list(CM_SECTIONS),
        "publish_enabled": bool(status.get("publish_enabled")),
        "runtime_mode": cm_runtime_mode(),
        "tenant_runtime": tenant_runtime,
        "has_published_content": tenant_has_published_cm(tenant_id),
        "publish_disabled_message": status.get("message"),
        "faq_canonical": cm_faq_canonical(),
    }


@app.get("/api/cm/draft/{section}")
async def cm_get_draft(section: str, request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    try:
        name = section.strip().replace("-", "_")
        envelope = get_draft(name, tenant_id=tenant_id, create_default=True)
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = _owner_sanitize_envelope(_envelope_dict(envelope), name)
    return JSONResponse(
        content={"success": True, "data": data},
        headers={"ETag": str(data.get("etag") or "")},
    )


@app.put("/api/cm/draft/{section}")
async def cm_put_draft(
    section: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    name = section.strip().replace("-", "_")

    if not if_match or not str(if_match).strip():
        raise HTTPException(status_code=428, detail="If-Match header is required")

    payload = body.get("payload")
    if payload is None and isinstance(body.get("data"), dict):
        payload = body.get("data")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must include a payload object")

    try:
        envelope = put_draft(
            name,
            payload=payload,
            if_match=if_match,
            updated_by=session.user_id or session.email,
            tenant_id=tenant_id,
        )
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MetadataPreparationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": METADATA_PREPARATION_CODE,
                "message": exc.user_message or METADATA_PREPARATION_MESSAGE,
                "live": False,
            },
        )
    except ConflictError as exc:
        current = _owner_sanitize_envelope(_envelope_dict(exc.current), name) if exc.current is not None else {}
        current_etag = str(current.get("etag") or "")
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "CONFLICT",
                "message": exc.message,
                "current_etag": current_etag,
                "current": current or None,
            },
            headers={"ETag": current_etag} if current_etag else {},
        )

    data = _owner_sanitize_envelope(_envelope_dict(envelope), name)
    if name == "ai_limits":
        from services.ai_limits_source import sync_enforcement_from_payload

        sync_enforcement_from_payload(tenant_id, envelope.payload if hasattr(envelope, "payload") else payload)

    from services.cm.save_live import go_live_saved_section

    activation = await go_live_saved_section(
        tenant_id=tenant_id,
        section=name,
        actor_id=session.user_id or session.email or "save",
    )
    if not activation.get("live"):
        status = 403 if activation.get("reason") == "emergency_disable" else 422
        return JSONResponse(
            status_code=status,
            content={
                "success": False,
                "error": "SAVE_NOT_LIVE",
                "message": activation.get("message") or "Save did not become live.",
                "live": False,
                "reason": activation.get("reason"),
                "errors": activation.get("errors") or [],
                "data": data,
            },
            headers={"ETag": str(data.get("etag") or "")},
        )
    return JSONResponse(
        content={
            "success": True,
            "message": "Saved and live",
            "live": True,
            "data": data,
            "content_version_id": activation.get("content_version_id"),
            "index_version_id": activation.get("index_version_id"),
        },
        headers={"ETag": str(data.get("etag") or "")},
    )


@app.post("/api/cm/publish")
async def cm_publish(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentPublish")
    tenant_id = _session_tenant(session)
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        return _publish_disabled_response(exc.message)

    notes = body.get("notes") if isinstance(body.get("notes"), str) else None
    scope = str(body.get("scope") or "all").strip().lower()
    try:
        if scope in {"faq", "faq_only"}:
            result = await publish_faq_only(
                tenant_id=tenant_id,
                published_by=session.user_id or session.email,
                notes=notes,
            )
        else:
            result = await publish_draft(
                tenant_id=tenant_id,
                published_by=session.user_id or session.email,
                notes=notes,
            )
    except PublishBlockedError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "PUBLISH_BLOCKED",
                "message": exc.message,
                "errors": exc.errors,
            },
        )
    return {
        "success": True,
        "scope": scope,
        "content_version_id": result.content_version_id,
        "index_version_id": result.index_version_id,
        "manifest": result.manifest,
        "pointer": result.pointer,
        "previous_pointer": result.previous_pointer,
    }


@app.post("/api/cm/unpublish")
async def cm_unpublish(request: Request) -> Any:
    """Turn customer AI off by clearing the published CM pointer (versions kept)."""
    session = require_permission(request, "contentPublish")
    tenant_id = _session_tenant(session)
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        return _publish_disabled_response(exc.message)

    from services.cm.version_store import clear_published_pointer, read_published_pointer

    previous = read_published_pointer(tenant_id)
    cleared = clear_published_pointer(tenant_id)
    from services.customer_reply_v2.manifest import clear_manifest_cache

    clear_manifest_cache(tenant_id)
    return {
        "success": True,
        "cleared": cleared,
        "live": False,
        "previous_pointer": previous.model_dump(mode="json") if previous is not None else None,
    }
