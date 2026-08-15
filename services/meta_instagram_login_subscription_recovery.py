"""Manual and shared helpers for Instagram Login webhook subscription recovery."""

from __future__ import annotations

import time

import httpx

from services.meta_app_registry import (
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
    get_meta_graph_api_version,
)
from services.meta_instagram_login_subscription import (
    COMMENTS_SUBSCRIPTION_FIELD,
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR,
    REQUIRED_DM_SUBSCRIPTION_FIELDS,
    InstagramLoginSubscriptionState,
    ensure_instagram_login_webhook_subscription,
    inspect_instagram_login_webhook_subscription,
    instagram_channel_subscription_lock_asset,
    instagram_login_subscription_lock_asset,
    restore_instagram_login_webhook_subscription,
)
from services.meta_oauth_graph_http import MetaOAuthError
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation


def _cleanup_binding(registry: MetaAppRegistry, binding_id: str) -> MetaAssetBinding | None:
    return next(
        (
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id == binding_id
        ),
        None,
    )


def _discard_cleanup_binding_reconciled(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    binding_id = binding.binding_id
    try:
        return registry.discard_staged_binding(
            binding_id,
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
    except Exception:
        latest = _cleanup_binding(registry, binding_id)
        if (
            latest is None
            or getattr(latest, "status", "") != "disconnected"
            or registry.binding_credential_is_available(binding_id)
        ):
            raise
        return latest


def instagram_login_orphan_cleanup_eligible(binding: MetaAssetBinding) -> bool:
    """Identify a hidden live direct credential left before durable marking."""

    return (
        binding.channel == "instagram"
        and binding.auth_flow == "instagram_login"
        and not binding.active
        and binding.status != "disconnected"
        and binding.webhook_subscription_status != INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    )


async def _recover_non_active_instagram_login_locked(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None,
) -> MetaAssetBinding:
    active_sibling = next(
        (
            item
            for item in registry.list_bindings(include_inactive=False, include_superseded=True)
            if item.binding_id != binding.binding_id
            and item.channel == "instagram"
            and item.auth_flow == "instagram_login"
            and item.app_key == binding.app_key
            and item.asset_id == binding.asset_id
        ),
        None,
    )
    if active_sibling is not None:
        active_credential = registry.get_credential(active_sibling)
        if active_credential.expires_at is not None and active_credential.expires_at <= int(time.time()):
            raise MetaOAuthError("Active Instagram Login credential is expired")
        app = get_meta_app_configs()[active_sibling.app_key]
        provider_ready = False
        if active_sibling.instagram_login_product_ready:
            provider_snapshot = await inspect_instagram_login_webhook_subscription(
                active_sibling,
                registry=registry,
                client=client,
            )
            provider_ready = provider_snapshot is not None and (
                REQUIRED_DM_SUBSCRIPTION_FIELDS | {COMMENTS_SUBSCRIPTION_FIELD}
            ).issubset(provider_snapshot)
        if not provider_ready:
            active_state = await ensure_instagram_login_webhook_subscription(
                active_sibling,
                active_credential,
                registry=registry,
                graph_api_version=app.graph_api_version or get_meta_graph_api_version(),
                client=client,
            )
            provider_ready = active_state.ready_for_dm and active_state.ready_for_comments
        refreshed_active = _cleanup_binding(registry, active_sibling.binding_id)
        global_active = [
            item
            for item in registry.list_bindings(include_inactive=False, include_superseded=True)
            if item.channel == "instagram" and item.asset_id == binding.asset_id
        ]
        if (
            not provider_ready
            or refreshed_active is None
            or not refreshed_active.instagram_login_product_ready
            or not registry.binding_credential_is_available(refreshed_active.binding_id)
            or [item.binding_id for item in global_active] != [refreshed_active.binding_id]
        ):
            raise MetaOAuthError("Active Instagram Login subscription recovery is incomplete")
    else:
        actual = await inspect_instagram_login_webhook_subscription(
            binding,
            registry=registry,
            client=client,
        )
        owns_client = client is None
        http_client = client or httpx.AsyncClient(timeout=20.0)
        try:
            await restore_instagram_login_webhook_subscription(
                binding,
                None,
                expected_current=actual,
                registry=registry,
                client=http_client,
            )
        finally:
            if owns_client:
                await http_client.aclose()
    return _discard_cleanup_binding_reconciled(binding, actor_id=actor_id, registry=registry)


async def retry_instagram_login_cleanup(
    binding_id: str,
    *,
    registry: MetaAppRegistry | None = None,
    actor_id: str = "instagram-login-cleanup-retry",
    client: httpx.AsyncClient | None = None,
) -> MetaAssetBinding:
    """Restore/delete a durable failed-OAuth preimage, then archive its credential."""

    current_registry = registry or get_meta_app_registry()
    binding = _cleanup_binding(current_registry, binding_id)
    if (
        binding is None
        or binding.auth_flow != "instagram_login"
        or binding.channel != "instagram"
        or binding.active
        or binding.webhook_subscription_status != INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
        or not current_registry.binding_credential_is_available(binding_id)
    ):
        raise MetaOAuthError("Instagram Login cleanup target is unavailable")

    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(
            instagram_channel_subscription_lock_asset(binding.tenant_id),
            instagram_login_subscription_lock_asset(binding.asset_id),
        ),
    ):
        binding = _cleanup_binding(current_registry, binding_id)
        if (
            binding is None
            or binding.active
            or binding.webhook_subscription_status != INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
            or not current_registry.binding_credential_is_available(binding_id)
        ):
            raise MetaOAuthError("Instagram Login cleanup target changed")
        mode = binding.webhook_subscription_error
        if mode not in {INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR, INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR}:
            raise MetaOAuthError("Instagram Login cleanup marker is invalid")
        return await _recover_non_active_instagram_login_locked(
            binding,
            actor_id=actor_id,
            registry=current_registry,
            client=client,
        )


async def retry_instagram_login_orphan_cleanup(
    binding_id: str,
    *,
    registry: MetaAppRegistry | None = None,
    actor_id: str = "instagram-login-orphan-cleanup",
    client: httpx.AsyncClient | None = None,
) -> MetaAssetBinding:
    """Settle a non-active live token left before a cleanup marker committed."""

    current_registry = registry or get_meta_app_registry()
    binding = _cleanup_binding(current_registry, binding_id)
    if (
        binding is None
        or not instagram_login_orphan_cleanup_eligible(binding)
        or not current_registry.binding_credential_is_available(binding_id)
    ):
        raise MetaOAuthError("Instagram Login orphan cleanup target is unavailable")
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(
            instagram_channel_subscription_lock_asset(binding.tenant_id),
            instagram_login_subscription_lock_asset(binding.asset_id),
        ),
    ):
        binding = _cleanup_binding(current_registry, binding_id)
        if (
            binding is None
            or not instagram_login_orphan_cleanup_eligible(binding)
            or not current_registry.binding_credential_is_available(binding_id)
        ):
            raise MetaOAuthError("Instagram Login orphan cleanup target changed")
        return await _recover_non_active_instagram_login_locked(
            binding,
            actor_id=actor_id,
            registry=current_registry,
            client=client,
        )


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
