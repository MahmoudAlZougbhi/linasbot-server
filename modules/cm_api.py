"""
Content Management control-plane API.

Draft CRUD with ETag concurrency, validate, publish (hard-403 when disabled),
versions/rollback stubs, and safe Testing Lab preview packets.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission
from modules.core import app
from services.cm.constants import CM_SECTIONS, PUBLISH_DISABLED_MESSAGE, cm_faq_canonical, cm_runtime_mode
from services.cm.preview_packet import build_preview_packet, list_versions
from services.cm.publish import PublishBlockedError, RollbackTargetError, publish_draft, rollback_to_version
from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled, publish_status
from services.cm.storage import ConflictError, UnknownSectionError, get_draft, put_draft
from services.cm.validation import validate_cm


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


@app.get("/api/cm/meta")
async def cm_meta() -> Any:
    status = publish_status()
    return {
        "success": True,
        "sections": list(CM_SECTIONS),
        "publish_enabled": bool(status.get("publish_enabled")),
        "runtime_mode": cm_runtime_mode(),
        "publish_disabled_message": status.get("message"),
        "faq_canonical": cm_faq_canonical(),
    }


@app.get("/api/cm/draft/{section}")
async def cm_get_draft(section: str) -> Any:
    try:
        name = section.strip().replace("-", "_")
        envelope = get_draft(name, create_default=True)
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = _envelope_dict(envelope)
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
        )
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConflictError as exc:
        current = _envelope_dict(exc.current) if exc.current is not None else {}
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

    data = _envelope_dict(envelope)
    return JSONResponse(
        content={"success": True, "message": "Draft saved", "data": data},
        headers={"ETag": str(data.get("etag") or "")},
    )


@app.post("/api/cm/validate")
async def cm_validate(body: dict[str, Any] = Body(default={})) -> Any:
    section = body.get("section")
    payload = body.get("payload")
    if payload is None and isinstance(body.get("data"), dict):
        payload = body.get("data")
    try:
        result = validate_cm(
            section=str(section) if section else None,
            payload=payload if isinstance(payload, dict) else None,
        )
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.post("/api/cm/publish")
async def cm_publish(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "contentPublish")
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        return _publish_disabled_response(exc.message)

    notes = body.get("notes") if isinstance(body.get("notes"), str) else None
    try:
        result = await publish_draft(
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
        "content_version_id": result.content_version_id,
        "index_version_id": result.index_version_id,
        "manifest": result.manifest,
        "pointer": result.pointer,
        "previous_pointer": result.previous_pointer,
    }


@app.get("/api/cm/versions")
async def cm_list_versions() -> Any:
    versions = list_versions()
    return {"success": True, "data": versions, "count": len(versions)}


@app.post("/api/cm/versions/{version_id}/rollback")
async def cm_rollback(version_id: str, request: Request) -> Any:
    require_permission(request, "contentPublish")
    try:
        ensure_publish_enabled()
    except PublishDisabledError as exc:
        return _publish_disabled_response(exc.message)

    try:
        result = rollback_to_version(content_version_id=version_id)
    except RollbackTargetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "success": True,
        "content_version_id": result.content_version_id,
        "index_version_id": result.index_version_id,
        "pointer": result.pointer,
        "previous_pointer": result.previous_pointer,
    }


@app.post("/api/cm/preview-packet")
async def cm_preview_packet(body: dict[str, Any] = Body(default={})) -> Any:
    source = str(body.get("source") or "draft")
    try:
        packet = build_preview_packet(source=source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": packet}
