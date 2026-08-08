"""Authenticated Meta social post creator APIs (caption, preview, explicit publish)."""

from __future__ import annotations

import time
import binascii
from typing import Any

from fastapi import Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from modules.api_security import require_permission
from modules.core import app
from services.meta_app_registry import APP_A_KEY, MetaAssetBinding, get_meta_app_registry
from services.meta_social_caption import generate_social_caption
from services.meta_social_media_store import (
    media_content_type,
    resolve_media_path,
    save_uploaded_media,
    tenant_media_hash,
    verify_media_access_token,
)
from services.meta_social_post_confirm import SocialPostConfirmError, build_preview, verify_preview_token
from services.meta_social_publish import (
    credential_has_publish_scopes,
    publish_facebook_post,
    publish_instagram_post,
    required_publish_scopes,
)


def _tenant_binding(binding_id: str, tenant_id: str) -> MetaAssetBinding:
    registry = get_meta_app_registry()
    binding = next(
        (item for item in registry.list_bindings() if item.binding_id == binding_id and item.tenant_id == tenant_id),
        None,
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Meta connection not found")
    return binding


def _asset_row(binding: MetaAssetBinding) -> dict[str, Any]:
    registry = get_meta_app_registry()
    public = binding.public_dict()
    try:
        credential = registry.get_credential(binding)
        public["granted_permissions"] = sorted(credential.scopes)
    except Exception:
        public["granted_permissions"] = []
    public["publish_scopes_required"] = sorted(required_publish_scopes(binding.channel))
    public["publish_scopes_ready"] = credential_has_publish_scopes(binding, registry)
    return public


@app.get("/api/meta/social-posts/assets")
async def list_social_post_assets(request: Request) -> Any:
    session = require_permission(request, "settings")
    registry = get_meta_app_registry()
    assets: list[dict[str, Any]] = []
    for binding in registry.list_bindings(include_superseded=False):
        if binding.tenant_id != session.tenant_id:
            continue
        if binding.app_key != APP_A_KEY or binding.status != "active":
            continue
        assets.append(_asset_row(binding))
    facebook = [row for row in assets if row.get("channel") == "facebook"]
    instagram = [row for row in assets if row.get("channel") == "instagram"]
    return {"success": True, "facebook_pages": facebook, "instagram_accounts": instagram}


@app.post("/api/meta/social-posts/generate-caption")
async def generate_social_post_caption(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "settings")
    topic = str(body.get("topic") or "").strip()
    platforms = [str(item).strip().lower() for item in (body.get("platforms") or []) if str(item).strip()]
    caption = await generate_social_caption(
        tenant_id=session.tenant_id,
        topic=topic,
        platforms=platforms,
    )
    if not caption:
        raise HTTPException(status_code=409, detail="Caption could not be generated from approved content")
    return {"success": True, "caption": caption}


@app.post("/api/meta/social-posts/upload-media")
async def upload_social_post_media(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "settings")
    import base64

    filename = str(body.get("filename") or "upload.jpg")
    content_type = str(body.get("content_type") or "image/jpeg").strip().lower()
    encoded = str(body.get("content_base64") or "").strip()
    if not encoded:
        raise HTTPException(status_code=400, detail="content_base64 is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload") from exc
    try:
        media_id = save_uploaded_media(
            tenant_id=session.tenant_id,
            filename=filename,
            content=raw,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "media_id": media_id}


@app.get("/api/meta/social-posts/media/{tenant_hash}/{media_id}")
async def serve_social_post_media(tenant_hash: str, media_id: str, token: str = Query(default="")) -> Any:
    """Publicly reachable image URL required by Instagram content publishing."""

    registry = get_meta_app_registry()
    tenant_id = ""
    for binding in registry.list_bindings(include_superseded=False):
        if tenant_media_hash(binding.tenant_id) == tenant_hash:
            tenant_id = binding.tenant_id
            break
    if not tenant_id or not verify_media_access_token(tenant_id=tenant_id, media_id=media_id, token=token):
        raise HTTPException(status_code=404, detail="Media not found")
    path = resolve_media_path(tenant_id=tenant_id, media_id=media_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return FileResponse(str(path), media_type=media_content_type(path))


@app.post("/api/meta/social-posts/preview")
async def preview_social_post(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "settings")
    publish_facebook = bool(body.get("publish_facebook"))
    publish_instagram = bool(body.get("publish_instagram"))
    caption = str(body.get("caption") or "").strip()
    media_id = str(body.get("media_id") or "").strip()
    facebook_binding_id = str(body.get("facebook_binding_id") or "").strip()
    instagram_binding_id = str(body.get("instagram_binding_id") or "").strip()

    if publish_facebook:
        fb_binding = _tenant_binding(facebook_binding_id, session.tenant_id)
        if fb_binding.channel != "facebook":
            raise HTTPException(status_code=400, detail="Invalid Facebook Page selection")
        if not credential_has_publish_scopes(fb_binding):
            raise HTTPException(status_code=409, detail="Facebook publish permissions are missing")
    if publish_instagram:
        ig_binding = _tenant_binding(instagram_binding_id, session.tenant_id)
        if ig_binding.channel != "instagram":
            raise HTTPException(status_code=400, detail="Invalid Instagram account selection")
        if not credential_has_publish_scopes(ig_binding):
            raise HTTPException(status_code=409, detail="Instagram publish permissions are missing")
        if not media_id:
            raise HTTPException(status_code=400, detail="Instagram posts require an image")

    try:
        preview, preview_token = build_preview(
            tenant_id=session.tenant_id,
            actor_id=session.user_id or session.email,
            facebook_binding_id=facebook_binding_id if publish_facebook else "",
            instagram_binding_id=instagram_binding_id if publish_instagram else "",
            caption=caption,
            media_id=media_id,
            publish_facebook=publish_facebook,
            publish_instagram=publish_instagram,
        )
    except SocialPostConfirmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_path = resolve_media_path(tenant_id=session.tenant_id, media_id=media_id) if media_id else None
    return {
        "success": True,
        "preview_token": preview_token,
        "expires_at": preview.expires_at,
        "requires_confirmation": True,
        "preview": {
            "caption": preview.caption,
            "publish_facebook": preview.publish_facebook,
            "publish_instagram": preview.publish_instagram,
            "has_media": bool(media_path),
            "facebook_page_name": (
                _tenant_binding(facebook_binding_id, session.tenant_id).page_name if publish_facebook else ""
            ),
            "instagram_username": (
                _tenant_binding(instagram_binding_id, session.tenant_id).instagram_username
                if publish_instagram
                else ""
            ),
        },
    }


@app.post("/api/meta/social-posts/publish")
async def publish_social_post(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "settings")
    if not bool(body.get("confirmed")):
        raise HTTPException(status_code=400, detail="Explicit publish confirmation is required")
    preview_token = str(body.get("preview_token") or "").strip()
    if not preview_token:
        raise HTTPException(status_code=400, detail="Preview token is required")

    try:
        preview = verify_preview_token(preview_token)
    except SocialPostConfirmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if preview.tenant_id != session.tenant_id:
        raise HTTPException(status_code=403, detail="Preview token tenant mismatch")
    if preview.actor_id != (session.user_id or session.email):
        raise HTTPException(status_code=403, detail="Preview token actor mismatch")

    media_path = resolve_media_path(tenant_id=session.tenant_id, media_id=preview.media_id) if preview.media_id else None
    results: list[dict[str, Any]] = []

    if preview.publish_facebook:
        binding = _tenant_binding(preview.facebook_binding_id, session.tenant_id)
        result = await publish_facebook_post(
            binding,
            tenant_id=session.tenant_id,
            caption=preview.caption,
            media_path=media_path,
        )
        results.append(
            {
                "platform": result.platform,
                "success": result.success,
                "post_id": result.post_id,
                "permalink": result.permalink,
                "error": result.error,
            }
        )

    if preview.publish_instagram:
        if media_path is None:
            raise HTTPException(status_code=400, detail="Instagram image is no longer available; upload again")
        binding = _tenant_binding(preview.instagram_binding_id, session.tenant_id)
        result = await publish_instagram_post(
            binding,
            tenant_id=session.tenant_id,
            caption=preview.caption,
            media_path=media_path,
        )
        results.append(
            {
                "platform": result.platform,
                "success": result.success,
                "post_id": result.post_id,
                "permalink": result.permalink,
                "error": result.error,
            }
        )

    registry = get_meta_app_registry()
    registry._append_audit(
        {
            "event": "social_post_published",
            "tenant_id": session.tenant_id,
            "actor_id": session.user_id or session.email,
            "platforms": [row["platform"] for row in results],
            "success": all(row.get("success") for row in results),
            "timestamp": time.time(),
        }
    )
    return {"success": all(row.get("success") for row in results), "results": results}
