"""Manual and shared helpers for Instagram Login webhook subscription recovery."""

from __future__ import annotations

import time

import httpx

from services.meta_app_registry import (
    MetaAppRegistry,
    get_meta_app_configs,
    get_meta_app_registry,
    get_meta_graph_api_version,
)
from services.meta_instagram_login_subscription import (
    InstagramLoginSubscriptionState,
    ensure_instagram_login_webhook_subscription,
)
from services.meta_oauth import MetaOAuthError


async def retry_instagram_login_webhook_subscription(
    binding_id: str,
    *,
    registry: MetaAppRegistry | None = None,
    actor_id: str = "instagram-login-retry",
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginSubscriptionState:
    current_registry = registry or get_meta_app_registry()
    binding = next(
        (item for item in current_registry.list_bindings(include_inactive=False) if item.binding_id == binding_id),
        None,
    )
    if binding is None:
        raise MetaOAuthError("Instagram Login binding not found")
    if binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Webhook retry applies only to Instagram Login bindings")
    credential = current_registry.get_credential(binding)
    if credential.expires_at is not None and credential.expires_at <= int(time.time()):
        current_registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
        raise MetaOAuthError("Instagram token expired; reconnect with Connect Instagram")
    app = get_meta_app_configs()[binding.app_key]
    return await ensure_instagram_login_webhook_subscription(
        binding,
        credential,
        registry=current_registry,
        graph_api_version=app.graph_api_version or get_meta_graph_api_version(),
        client=client,
    )


async def reconcile_pending_instagram_login_subscriptions(
    *,
    registry: MetaAppRegistry | None = None,
    limit: int = 20,
) -> int:
    from services.meta_instagram_login_lifecycle import get_instagram_login_lifecycle

    result = await get_instagram_login_lifecycle().run_once(actor_id="instagram-login-reconcile")
    return int(result.get("subscriptions_recovered") or 0)
