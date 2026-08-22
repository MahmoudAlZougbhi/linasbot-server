"""Instagram Login per-account webhook subscription via graph.instagram.com."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from services.meta_app_registry import (
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_registry,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_GRAPH_BASE_URL,
    instagram_login_app_id,
    instagram_login_graph_api_version,
)
from services.meta_instagram_login_subscription_graph import (
    InstagramLoginWebhookSubscriptionSnapshot,
    InstagramSubscribedAppsProviderError,
    fetch_subscription_fields,
    inspect_instagram_login_webhook_subscription,
    restore_instagram_login_webhook_subscription,
    subscribe_instagram_login_fields,
    unsubscribe_instagram_login_webhook_raw,
)
from services.meta_oauth_graph_http import MetaOAuthError
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation

_runtime_logger = logging.getLogger("uvicorn.error")

REQUIRED_DM_SUBSCRIPTION_FIELDS = frozenset({"messages", "messaging_postbacks"})
COMMENTS_SUBSCRIPTION_FIELD = "comments"
INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS = "cleanup_pending"
INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR = "cleanup_delete_subscription"
INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR = "cleanup_restore_preimage"
INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR = "verification_rate_limited"
INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR = "verification_deferred"
INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR = "subscription_write_rejected"
# One immediate verify, then one retry after 10s. Never a third Graph verify.
_VERIFY_BACKOFF_SECONDS = (0.0, 10.0)

__all__ = [
    "COMMENTS_SUBSCRIPTION_FIELD",
    "INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR",
    "INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS",
    "INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR",
    "INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR",
    "INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR",
    "INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR",
    "InstagramLoginSubscriptionState",
    "InstagramLoginWebhookSubscriptionSnapshot",
    "REQUIRED_DM_SUBSCRIPTION_FIELDS",
    "ensure_instagram_login_webhook_subscription",
    "inspect_instagram_login_webhook_subscription",
    "instagram_channel_subscription_lock_asset",
    "instagram_login_subscription_lock_asset",
    "restore_instagram_login_webhook_subscription",
    "subscribed_fields_for_granted_scopes",
    "unsubscribe_instagram_login_webhook_raw",
]

# Historical private name used by focused tests.
_subscribe_once = subscribe_instagram_login_fields


def instagram_login_subscription_lock_asset(ig_user_id: str) -> str:
    """Return the durable writer-lock identity shared by connect and disconnect."""

    normalized = str(ig_user_id or "").strip()
    if not normalized.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")
    return f"instagram-login:{normalized}"


def instagram_channel_subscription_lock_asset(tenant_id: str) -> str:
    """Serialize tenant-wide Instagram connect/disconnect target-set changes."""

    normalized = str(tenant_id or "").strip().lower()
    if not normalized:
        raise MetaOAuthError("Instagram workspace lock identity is invalid")
    return f"instagram-channel:{normalized}"


@dataclass(frozen=True)
class InstagramLoginSubscriptionState:
    status: str
    subscribed_fields: tuple[str, ...]
    verified_fields: tuple[str, ...]
    error: str = ""

    @property
    def ready_for_dm(self) -> bool:
        return REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(self.verified_fields)

    @property
    def ready_for_comments(self) -> bool:
        return COMMENTS_SUBSCRIPTION_FIELD in self.verified_fields

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "subscribed_fields": list(self.subscribed_fields),
            "verified_fields": list(self.verified_fields),
            "ready_for_dm": self.ready_for_dm,
            "ready_for_comments": self.ready_for_comments,
            "error": self.error,
        }


def subscribed_fields_for_granted_scopes(scopes: tuple[str, ...] | frozenset[str]) -> tuple[str, ...]:
    granted = set(scopes)
    fields = ["messages", "messaging_postbacks"]
    if "instagram_business_manage_comments" in granted:
        fields.append(COMMENTS_SUBSCRIPTION_FIELD)
    return tuple(fields)


def _subscription_status_for_verified(*, verified: frozenset[str], subscribed_fields: tuple[str, ...]) -> str:
    if not REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(verified):
        return "failed"
    if COMMENTS_SUBSCRIPTION_FIELD in subscribed_fields and COMMENTS_SUBSCRIPTION_FIELD not in verified:
        return "partial"
    return "ready"


async def ensure_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry | None = None,
    graph_api_version: str,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginSubscriptionState:
    """Idempotently subscribe and verify webhook fields for one IG professional account."""

    if binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Webhook subscription applies only to Instagram Login bindings")
    ig_user_id = binding.asset_id.strip()
    if not ig_user_id.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")

    subscribed_fields = subscribed_fields_for_granted_scopes(credential.scopes)
    expected_app_id = instagram_login_app_id()
    if credential.token_app_id != expected_app_id:
        raise MetaOAuthError("Instagram Login credential belongs to an unexpected app")
    current_registry = registry or get_meta_app_registry()
    _ = graph_api_version
    ig_graph_version = instagram_login_graph_api_version()
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(
            instagram_channel_subscription_lock_asset(binding.tenant_id),
            instagram_login_subscription_lock_asset(ig_user_id),
        ),
    ):
        latest = next(
            (
                item
                for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.channel != "instagram"
            or latest.auth_flow != "instagram_login"
            or latest.asset_id != binding.asset_id
            or latest.app_key != binding.app_key
            or latest.generation != binding.generation
            or latest.status not in {"active", "testing"}
            or not current_registry.binding_credential_is_available(binding.binding_id)
        ):
            raise MetaOAuthError("Instagram Login binding changed before webhook subscription")
        return await _ensure_instagram_login_webhook_subscription_locked(
            latest,
            credential,
            registry=current_registry,
            graph_api_version=ig_graph_version,
            subscribed_fields=subscribed_fields,
            client=client,
        )


async def _ensure_instagram_login_webhook_subscription_locked(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry,
    graph_api_version: str,
    subscribed_fields: tuple[str, ...],
    client: httpx.AsyncClient | None,
) -> InstagramLoginSubscriptionState:
    """Subscribe while the caller owns the direct app/account writer lock."""

    ig_user_id = binding.asset_id.strip()
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}",
        timeout=20.0,
    )
    last_error = ""

    latest_verified = (
        frozenset(binding.webhook_subscribed_fields)
        if binding.active and binding.webhook_subscription_status in {"ready", "partial"}
        else frozenset[str]()
    )

    def persist_unresolved(error: str) -> InstagramLoginSubscriptionState:
        status = (
            _subscription_status_for_verified(
                verified=latest_verified,
                subscribed_fields=subscribed_fields,
            )
            if REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(latest_verified)
            else "failed"
        )
        unresolved = InstagramLoginSubscriptionState(
            status=status,
            subscribed_fields=subscribed_fields,
            verified_fields=tuple(sorted(latest_verified)),
            error=error or "subscription_verify_failed",
        )
        registry.update_instagram_login_webhook_subscription(
            binding.binding_id,
            state=unresolved,
            actor_id="instagram-login-subscribe",
        )
        return unresolved

    def persist_ready(verified: frozenset[str]) -> InstagramLoginSubscriptionState:
        status = _subscription_status_for_verified(
            verified=verified,
            subscribed_fields=subscribed_fields,
        )
        state = InstagramLoginSubscriptionState(
            status=status,
            subscribed_fields=subscribed_fields,
            verified_fields=tuple(sorted(verified)),
        )
        registry.update_instagram_login_webhook_subscription(
            binding.binding_id,
            state=state,
            actor_id="instagram-login-subscribe",
        )
        return state

    try:
        try:
            verified = await fetch_subscription_fields(
                ig_user_id=ig_user_id,
                access_token=credential.access_token,
                graph_api_version=graph_api_version,
                client=http_client,
            )
            latest_verified = verified
            if set(subscribed_fields).issubset(verified):
                return persist_ready(verified)
        except InstagramSubscribedAppsProviderError as exc:
            last_error = (
                INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR
                if exc.rate_limited
                else "subscription_verify_provider_error"
            )
            _runtime_logger.warning(
                "[instagram-login] subscribe_preflight_failed binding=%s reason=%s",
                binding.binding_id[-8:],
                last_error,
            )
            if exc.rate_limited:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR)
            if not exc.retryable:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR)
        except httpx.HTTPError:
            last_error = "subscription_verify_transport_error"
        except MetaOAuthError:
            last_error = "subscription_verify_invalid_response"

        try:
            # At most one provider mutation per Connect after GET proved fields missing.
            await subscribe_instagram_login_fields(
                ig_user_id=ig_user_id,
                access_token=credential.access_token,
                subscribed_fields=subscribed_fields,
                graph_api_version=graph_api_version,
                client=http_client,
            )
        except InstagramSubscribedAppsProviderError as exc:
            last_error = "subscription_write_rate_limited" if exc.rate_limited else "subscription_write_failed"
            _runtime_logger.warning(
                "[instagram-login] subscribe_write_failed binding=%s reason=%s",
                binding.binding_id[-8:],
                last_error,
            )
            if exc.rate_limited:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR)
            if not exc.retryable:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR)
        except httpx.HTTPError:
            last_error = "subscription_write_outcome_unknown"
        except MetaOAuthError:
            return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR)

        for attempt, delay in enumerate(_VERIFY_BACKOFF_SECONDS, start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                verified = await fetch_subscription_fields(
                    ig_user_id=ig_user_id,
                    access_token=credential.access_token,
                    graph_api_version=graph_api_version,
                    client=http_client,
                )
                latest_verified = verified
                if set(subscribed_fields).issubset(verified):
                    return persist_ready(verified)
                last_error = "required_dm_fields_missing_after_verify"
            except InstagramSubscribedAppsProviderError as exc:
                last_error = (
                    INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR
                    if exc.rate_limited
                    else "subscription_verify_provider_error"
                )
                _runtime_logger.warning(
                    "[instagram-login] subscribe_verify_failed binding=%s attempt=%d reason=%s",
                    binding.binding_id[-8:],
                    attempt,
                    last_error,
                )
                if exc.rate_limited:
                    return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR)
                if not exc.retryable:
                    break
            except httpx.HTTPError:
                last_error = "subscription_verify_transport_error"
            except MetaOAuthError:
                last_error = "subscription_verify_invalid_response"

        return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR)
    finally:
        if owns_client:
            await http_client.aclose()
