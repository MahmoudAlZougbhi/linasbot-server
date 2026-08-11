"""CM article media upload/serve (knowledge/care case examples)."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from modules.api_security import require_permission
from modules.core import app
from services.cm.article_media import load_media_bytes, load_media_meta, store_article_media
from services.dashboard_session_service import SessionRecord


def _session_tenant(session: SessionRecord) -> str:
    tenant_id = str(session.tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


@app.post("/api/cm/media")
async def cm_upload_media(
    request: Request,
    file: UploadFile = File(...),
) -> Any:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    raw = await file.read()
    result = store_article_media(
        tenant_id=tenant_id,
        user_id=str(session.user_id or ""),
        filename=file.filename or "upload.bin",
        content=raw,
        content_type=file.content_type,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "upload_failed")
    return {
        "success": True,
        "media_id": result["media_id"],
        "filename": result["filename"],
        "mime": result["mime"],
        "kind": result["kind"],
        "size": result["size"],
    }


@app.get("/api/cm/media/{media_id}")
async def cm_get_media(media_id: str, request: Request) -> Response:
    session = require_permission(request, "contentManagers")
    tenant_id = _session_tenant(session)
    meta = load_media_meta(tenant_id=tenant_id, media_id=media_id)
    if not meta:
        raise HTTPException(status_code=404, detail="media_not_found")
    content = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
    if content is None:
        raise HTTPException(status_code=404, detail="media_not_found")
    filename = str(meta.get("filename") or media_id)
    mime = str(meta.get("mime") or "application/octet-stream")
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
