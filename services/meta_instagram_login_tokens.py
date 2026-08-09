"""Locked Instagram Login token refresh with durable multi-worker claims."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.meta_app_registry import MetaAppRegistry, MetaAssetBinding, MetaBindingCredential, get_meta_app_registry
from services.meta_instagram_login_config import META_INSTAGRAM_GRAPH_BASE_URL, instagram_login_app_id
from services.meta_instagram_login_oauth import credential_needs_refresh, refresh_instagram_long_lived_token
from services.meta_oauth import MetaOAuthError

_runtime_logger = logging.getLogger("uvicorn.error")
_REFRESH_BACKOFF_SECONDS = (1.0, 3.0, 8.0)
_REFRESH_MAX_ATTEMPTS = 3


def _refresh_lock_key(binding_id: str) -> str:
    return f"instagram-login-refresh:{binding_id}"


async def refresh_binding_instagram_login_token(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> MetaBindingCredential:
    if binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Token refresh applies only to Instagram Login bindings")

    lock_key = _refresh_lock_key(binding.binding_id)
    claimed = await asyncio.to_thread(try_acquire_job_lock, lock_key, ttl_seconds=120.0)
    if not claimed:
        current_registry = registry or get_meta_app_registry()
        return current_registry.get_credential(binding)

    try:
        current_registry = registry or get_meta_app_registry()
        latest_binding = next(
            (
                item
                for item in current_registry.list_bindings(include_inactive=False, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            binding,
        )
        credential = current_registry.get_credential(latest_binding)
        now = int(time.time())
        if credential.expires_at is not None and credential.expires_at <= now:
            current_registry.set_binding_status(
                latest_binding.binding_id,
                status="disconnected",
                actor_id="instagram-login-refresh",
                expected_generation=latest_binding.generation,
            )
            raise MetaOAuthError("Instagram token expired; reconnect required")

        if not credential_needs_refresh(credential):
            return credential

        owns_client = client is None
        http_client = client or httpx.AsyncClient(base_url=META_INSTAGRAM_GRAPH_BASE_URL, timeout=20.0)
        last_error = ""
        try:
            for attempt, delay in enumerate(_REFRESH_BACKOFF_SECONDS, start=1):
                try:
                    refreshed_token, expires_at = await refresh_instagram_long_lived_token(
                        credential.access_token,
                        client=http_client,
                    )
                    updated = MetaBindingCredential(
                        access_token=refreshed_token,
                        token_app_id=instagram_login_app_id(),
                        token_profile_id=credential.token_profile_id,
                        scopes=credential.scopes,
                        expires_at=expires_at,
                        authorized_meta_user_id=credential.authorized_meta_user_id,
                        auth_flow="instagram_login",
                        declined_scopes=credential.declined_scopes,
                    )
                    current_registry.authorize_oauth_asset(
                        tenant_id=latest_binding.tenant_id,
                        channel="instagram",
                        asset_id=latest_binding.asset_id,
                        page_id="",
                        instagram_account_id=latest_binding.asset_id,
                        app_key=latest_binding.app_key,
                        credential=updated,
                        actor_id="instagram-login-refresh",
                        instagram_username=latest_binding.instagram_username,
                        status=latest_binding.status,
                        auth_flow="instagram_login",
                        webhook_subscription_status=latest_binding.webhook_subscription_status,
                        webhook_subscribed_fields=latest_binding.webhook_subscribed_fields,
                        webhook_subscription_error=latest_binding.webhook_subscription_error,
                        webhook_subscription_checked_at=latest_binding.webhook_subscription_checked_at,
                    )
                    return updated
                except (MetaOAuthError, httpx.HTTPError) as exc:
                    last_error = type(exc).__name__
                    _runtime_logger.warning(
                        "[instagram-login] refresh_attempt_failed binding=%s attempt=%d reason=%s",
                        latest_binding.binding_id[-8:],
                        attempt,
                        last_error,
                    )
                    if attempt < _REFRESH_MAX_ATTEMPTS:
                        await asyncio.sleep(delay)
            if credential.expires_at is not None and credential.expires_at <= int(time.time()):
                current_registry.set_binding_status(
                    latest_binding.binding_id,
                    status="disconnected",
                    actor_id="instagram-login-refresh",
                    expected_generation=latest_binding.generation,
                )
                raise MetaOAuthError("Instagram token expired; reconnect required")
            raise MetaOAuthError("Instagram token refresh failed after retries")
        finally:
            if owns_client:
                await http_client.aclose()
    finally:
        await asyncio.to_thread(release_job_lock, lock_key)
