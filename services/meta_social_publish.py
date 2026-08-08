"""Publish Facebook and Instagram posts via Meta Graph API (App A, user-confirmed only)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    META_PUBLISH_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_oauth import MetaOAuthError, _safe_json
from services.meta_social_media_store import media_content_type, public_media_url, tenant_media_hash

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
        return META_PUBLISH_SCOPES["facebook"]
    if channel == "instagram":
        return META_PUBLISH_SCOPES["instagram"]
    return frozenset()


def credential_has_publish_scopes(binding: MetaAssetBinding, registry: MetaAppRegistry | None = None) -> bool:
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    granted = set(credential.scopes)
    return required_publish_scopes(binding.channel).issubset(granted)


def _assert_publish_binding(binding: MetaAssetBinding, tenant_id: str) -> None:
    if binding.app_key != APP_A_KEY:
        raise MetaOAuthError("Social publishing is only supported for App A")
    if binding.tenant_id != tenant_id:
        raise MetaOAuthError("Cross-workspace publishing is not allowed")
    if binding.status != "active":
        raise MetaOAuthError("Only active connections can publish")
    if not credential_has_publish_scopes(binding):
        raise MetaOAuthError("Missing Meta publish permissions for this asset")


async def publish_facebook_post(
    binding: MetaAssetBinding,
    *,
    tenant_id: str,
    caption: str,
    media_path: Path | None,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> PublishResult:
    _assert_publish_binding(binding, tenant_id)
    if binding.channel != "facebook":
        raise MetaOAuthError("Facebook publishing requires a Facebook Page binding")

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"https://graph.facebook.com/{app.graph_api_version}",
        timeout=60.0,
    )
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
    _assert_publish_binding(binding, tenant_id)
    if binding.channel != "instagram":
        raise MetaOAuthError("Instagram publishing requires an Instagram binding")
    if not media_path.exists():
        raise MetaOAuthError("Instagram posts require an image")

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    ig_user_id = binding.instagram_account_id or binding.asset_id
    media_id = media_path.stem
    image_url = public_media_url(base_url=public_base_url, tenant_id=tenant_id, media_id=media_id)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"https://graph.facebook.com/{app.graph_api_version}",
        timeout=60.0,
    )
    try:
        create_response = await http_client.post(
            f"{ig_user_id}/media",
            data={"image_url": image_url, "caption": caption},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        create_payload = _safe_json(create_response, step="instagram media create")
        creation_id = str(create_payload.get("id") or "")
        if not creation_id:
            return PublishResult(platform="instagram", success=False, error="Instagram media creation failed")

        await _wait_for_ig_container(http_client, creation_id=creation_id, token=credential.access_token)
        publish_response = await http_client.post(
            f"{ig_user_id}/media_publish",
            data={"creation_id": creation_id},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        publish_payload = _safe_json(publish_response, step="instagram media publish")
        published_id = str(publish_payload.get("id") or "")
        if not published_id:
            return PublishResult(platform="instagram", success=False, error="Instagram publish returned no media id")
        permalink = f"https://www.instagram.com/p/{published_id}/"
        return PublishResult(platform="instagram", success=True, post_id=published_id, permalink=permalink)
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram publish request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
