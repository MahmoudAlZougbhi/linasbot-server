"""Publish Facebook and Instagram posts via Meta Graph API (App A, user-confirmed only)."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
    get_meta_graph_api_version,
)
from services.meta_graph_routing import graph_base_url_for_binding, required_publish_scopes_for_binding
from services.meta_instagram_login_capabilities import binding_ready_for_publish
from services.meta_oauth import MetaOAuthError, _safe_json
from services.meta_social_media_store import media_content_type, public_media_url

_runtime_logger = logging.getLogger("uvicorn.error")
_PUBLIC_BASE_URL = "https://www.linasaibot.com"


@dataclass(frozen=True)
class PublishResult:
    platform: str
    success: bool
    post_id: str = ""
    permalink: str = ""
    error: str = ""


def required_publish_scopes(channel: str) -> frozenset[str]:
    if channel == "facebook":
        return required_publish_scopes_for_binding(
            MetaAssetBinding(
                binding_id="scope-check",
                tenant_id="scope",
                channel="facebook",
                asset_id="",
                page_id="",
                instagram_account_id="",
                app_key=APP_A_KEY,
                credential_id="",
                status="active",
                generation=1,
                created_at=0.0,
                updated_at=0.0,
                auth_flow="facebook_login",
            )
        )
    return required_publish_scopes_for_binding(
        MetaAssetBinding(
            binding_id="scope-check",
            tenant_id="scope",
            channel="instagram",
            asset_id="",
            page_id="",
            instagram_account_id="",
            app_key=APP_A_KEY,
            credential_id="",
            status="active",
            generation=1,
            created_at=0.0,
            updated_at=0.0,
            auth_flow="facebook_login",
        )
    )


def _assert_publish_binding(
    binding: MetaAssetBinding, tenant_id: str, *, registry: MetaAppRegistry | None = None
) -> None:
    if binding.app_key != APP_A_KEY:
        raise MetaOAuthError("Social publishing is only supported for App A")
    if binding.tenant_id != tenant_id:
        raise MetaOAuthError("Cross-workspace publishing is not allowed")
    if binding.status != "active":
        raise MetaOAuthError("Only active connections can publish")
    registry = registry or get_meta_app_registry()
    credential = registry.get_credential(binding)
    if not binding_ready_for_publish(binding, credential):
        raise MetaOAuthError("Missing Meta publish permissions for this asset")


def _graph_client(binding: MetaAssetBinding, *, client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    app = get_meta_app_configs()[binding.app_key]
    version = app.graph_api_version or get_meta_graph_api_version()
    if client is not None:
        return client, False
    return httpx.AsyncClient(
        base_url=f"{graph_base_url_for_binding(binding)}/{version}",
        timeout=60.0,
    ), True


def _instagram_media_type(path: Path) -> str:
    mime = media_content_type(path)
    if mime.startswith("video/"):
        return "REELS" if path.suffix.lower() in {".mp4", ".mov"} else "VIDEO"
    return "IMAGE"


async def publish_facebook_post(
    binding: MetaAssetBinding,
    *,
    tenant_id: str,
    caption: str,
    media_path: Path | None,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> PublishResult:
    _assert_publish_binding(binding, tenant_id, registry=registry)
    if binding.channel != "facebook":
        raise MetaOAuthError("Facebook publishing requires a Facebook Page binding")

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    http_client, owns_client = _graph_client(binding, client=client)
    try:
        if media_path and media_path.exists():
            with media_path.open("rb") as handle:
                response = await http_client.post(
                    f"{binding.page_id}/photos",
                    data={"message": caption, "published": "true"},
                    files={"source": (media_path.name, handle, media_content_type(media_path))},
                    headers={"Authorization": f"Bearer {credential.access_token}"},
                )
        else:
            response = await http_client.post(
                f"{binding.page_id}/feed",
                data={"message": caption},
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
        payload = _safe_json(response, step="facebook publish")
        post_id = str(payload.get("post_id") or payload.get("id") or "")
        if not post_id:
            return PublishResult(platform="facebook", success=False, error="Facebook publish returned no post id")
        permalink = f"https://www.facebook.com/{post_id}" if post_id else ""
        return PublishResult(platform="facebook", success=True, post_id=post_id, permalink=permalink)
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Facebook publish request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def _wait_for_ig_container(
    client: httpx.AsyncClient,
    *,
    creation_id: str,
    token: str,
    attempts: int = 12,
) -> None:
    for _ in range(attempts):
        response = await client.get(
            creation_id,
            params={"fields": "status_code"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code < 200 or response.status_code >= 300:
            await asyncio.sleep(2)
            continue
        payload = response.json()
        status = str(payload.get("status_code") or "").upper()
        if status in {"", "FINISHED"}:
            return
        if status == "ERROR":
            raise MetaOAuthError("Instagram media container failed")
        await asyncio.sleep(2)
    raise MetaOAuthError("Instagram media container did not become ready")


async def publish_instagram_post(
    binding: MetaAssetBinding,
    *,
    tenant_id: str,
    caption: str,
    media_path: Path,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
    public_base_url: str = _PUBLIC_BASE_URL,
) -> PublishResult:
    _assert_publish_binding(binding, tenant_id, registry=registry)
    if binding.channel != "instagram":
        raise MetaOAuthError("Instagram publishing requires an Instagram binding")
    if not media_path.exists():
        raise MetaOAuthError("Instagram posts require media")

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    ig_user_id = binding.instagram_account_id or binding.asset_id
    media_id = media_path.stem
    media_url = public_media_url(base_url=public_base_url, tenant_id=tenant_id, media_id=media_id)
    media_type = _instagram_media_type(media_path)

    http_client, owns_client = _graph_client(binding, client=client)
    try:
        create_data: dict[str, str] = {"caption": caption}
        if media_type == "IMAGE":
            create_data["image_url"] = media_url
        else:
            create_data["media_type"] = media_type
            create_data["video_url"] = media_url
            guessed = mimetypes.guess_type(media_path.name)[0] or media_content_type(media_path)
            if guessed:
                create_data["share_to_feed"] = "true" if media_type == "VIDEO" else "false"

        create_response = await http_client.post(
            f"{ig_user_id}/media",
            data=create_data,
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        create_payload = _safe_json(create_response, step="instagram media create")
        creation_id = str(create_payload.get("id") or "")
        if not creation_id:
            error_message = str((create_payload.get("error") or {}).get("message") or "Instagram media creation failed")
            return PublishResult(platform="instagram", success=False, error=error_message)

        await _wait_for_ig_container(http_client, creation_id=creation_id, token=credential.access_token)
        publish_response = await http_client.post(
            f"{ig_user_id}/media_publish",
            data={"creation_id": creation_id},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        publish_payload = _safe_json(publish_response, step="instagram media publish")
        published_id = str(publish_payload.get("id") or "")
        if not published_id:
            error_message = str(
                (publish_payload.get("error") or {}).get("message") or "Instagram publish returned no media id"
            )
            return PublishResult(platform="instagram", success=False, error=error_message)
        permalink = f"https://www.instagram.com/p/{published_id}/"
        return PublishResult(platform="instagram", success=True, post_id=published_id, permalink=permalink)
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram publish request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
