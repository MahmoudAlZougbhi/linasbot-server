"""Subscribe Meta webhook fields required for public comment replies (App A only)."""

from __future__ import annotations

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_graph_routing import credential_has_comment_scopes, required_comment_scopes_for_binding
from services.meta_oauth import MetaOAuthError, _safe_json
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation

PAGE_DM_FIELDS = ("messages", "messaging_postbacks")
PAGE_COMMENT_FIELDS = ("messages", "messaging_postbacks", "feed")
INSTAGRAM_APP_DM_FIELDS = ("messages", "messaging_postbacks")
INSTAGRAM_APP_COMMENT_FIELDS = ("comments", "messages", "messaging_postbacks")
APP_A_COMMENT_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"

__all__ = [
    "credential_has_comment_scopes",
    "ensure_instagram_comment_app_webhook",
    "ensure_page_comment_webhook_subscription",
    "required_comment_scopes",
]


def required_comment_scopes(channel: str) -> frozenset[str]:
    if channel == "facebook":
        return required_comment_scopes_for_binding(
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
    return required_comment_scopes_for_binding(
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


def _subscription_fields(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    fields: set[str] = set()
    for item in value:
        raw = item.get("name") if isinstance(item, dict) else item
        name = str(raw or "").strip()
        if name:
            fields.add(name)
    return fields


async def ensure_page_comment_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Add Page feed field while preserving DM webhook fields."""

    if binding.app_key != APP_A_KEY:
        raise MetaOAuthError("Comment webhooks are only supported for App A")
    if binding.auth_flow == "instagram_login":
        raise MetaOAuthError("Instagram Login comment webhooks are managed via subscribed_apps")
    if binding.channel != "facebook":
        raise MetaOAuthError("Page comment webhooks apply to Facebook bindings only")
    current_registry = registry or get_meta_app_registry()
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(binding.page_id,),
    ):
        await _ensure_page_comment_webhook_subscription_locked(
            binding,
            registry=current_registry,
            client=client,
        )


async def _ensure_page_comment_webhook_subscription_locked(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None,
) -> None:
    """Write/verify Page comment fields after acquiring the shared Page lock."""

    current_registry = registry
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"https://graph.facebook.com/{app.graph_api_version}", timeout=20.0
    )
    try:
        response = await http_client.post(
            f"{binding.page_id}/subscribed_apps",
            data={"subscribed_fields": ",".join(PAGE_COMMENT_FIELDS)},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        result = _safe_json(response, step="comment webhook subscription")
        if result.get("success") is not True:
            raise MetaOAuthError("Meta did not confirm the Page comment webhook subscription")
        verified_response = await http_client.get(
            f"{binding.page_id}/subscribed_apps",
            params={"fields": "id,subscribed_fields"},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        verified_payload = _safe_json(verified_response, step="comment webhook subscription verify")
        rows = verified_payload.get("data")
        matching = [
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict) and str(row.get("id") or "") == app.app_id
        ]
        verified_fields = _subscription_fields(matching[0].get("subscribed_fields")) if len(matching) == 1 else set()
        if not set(PAGE_COMMENT_FIELDS).issubset(verified_fields):
            raise MetaOAuthError("Meta Page comment webhook subscription could not be verified")
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
    """Reject legacy Facebook-Login Instagram webhook mutation.

    The Instagram product has its own callback and secret. Its subscription is
    managed only by the Instagram Login lifecycle, never through App A's Page
    verify token or Page callback.
    """

    if app_key != APP_A_KEY:
        raise MetaOAuthError("Instagram comment app webhooks are only supported for App A")
    del client
    raise MetaOAuthError(
        "Legacy Facebook Login Instagram comments cannot mutate the Direct Instagram webhook; "
        "reconnect via Instagram Login"
    )
