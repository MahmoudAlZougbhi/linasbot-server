"""Subscribe Meta webhook fields required for public comment replies (App A only)."""

from __future__ import annotations

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    META_COMMENT_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_oauth import MetaOAuthError, _safe_json

PAGE_DM_FIELDS = ("messages", "messaging_postbacks")
PAGE_COMMENT_FIELDS = ("messages", "messaging_postbacks", "feed")
INSTAGRAM_APP_DM_FIELDS = ("messages", "messaging_postbacks")
INSTAGRAM_APP_COMMENT_FIELDS = ("comments", "messages", "messaging_postbacks")


def required_comment_scopes(channel: str) -> frozenset[str]:
    if channel == "facebook":
        return META_COMMENT_SCOPES["facebook"]
    if channel == "instagram":
        return META_COMMENT_SCOPES["instagram"]
    return frozenset()


def credential_has_comment_scopes(binding: MetaAssetBinding, registry: MetaAppRegistry | None = None) -> bool:
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    granted = set(credential.scopes)
    return required_comment_scopes(binding.channel).issubset(granted)


async def ensure_page_comment_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Add Page feed field while preserving DM webhook fields."""

    if binding.app_key != APP_A_KEY:
        raise MetaOAuthError("Comment webhooks are only supported for App A")
    if binding.channel != "facebook":
        raise MetaOAuthError("Page comment webhooks apply to Facebook bindings only")
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"https://graph.facebook.com/{app.graph_api_version}", timeout=20.0)
    try:
        response = await http_client.post(
            f"{binding.page_id}/subscribed_apps",
            data={"subscribed_fields": ",".join(PAGE_COMMENT_FIELDS)},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        _safe_json(response, step="comment webhook subscription")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta comment webhook subscription request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def ensure_instagram_comment_app_webhook(
    *,
    app_key: str = APP_A_KEY,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Ensure App A instagram object includes comments field at app webhook level."""

    app = get_meta_app_configs()[app_key]
    if app_key != APP_A_KEY:
        raise MetaOAuthError("Instagram comment app webhooks are only supported for App A")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"https://graph.facebook.com/{app.graph_api_version}", timeout=20.0)
    try:
        response = await http_client.post(
            f"{app.app_id}/subscriptions",
            data={
                "object": "instagram",
                "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                "verify_token": app.verify_token,
                "fields": ",".join(INSTAGRAM_APP_COMMENT_FIELDS),
            },
            headers={"Authorization": f"Bearer {app.app_id}|{app.app_secret}"},
        )
        _safe_json(response, step="instagram comment app webhook")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta instagram comment app webhook request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
