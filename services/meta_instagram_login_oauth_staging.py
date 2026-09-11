"""Instagram Login OAuth staging, compensation, and cleanup-pending markers."""

from __future__ import annotations

from typing import cast

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR,
    InstagramLoginSubscriptionState,
    inspect_instagram_login_webhook_subscription,
    restore_instagram_login_webhook_subscription,
)
from services.meta_oauth import MetaOAuthError


class _InstagramProviderVerificationDeferred(MetaOAuthError):
    """Keep the staged credential for the distributed cleanup lifecycle."""


def _discard_staged_instagram_binding_reconciled(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    """Discard one staged credential and accept only an exact lost acknowledgement."""

    try:
        return registry.discard_staged_binding(
            binding.binding_id,
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
    except Exception:
        latest = next(
            (
                item
                for item in registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.tenant_id != binding.tenant_id
            or latest.channel != binding.channel
            or latest.asset_id != binding.asset_id
            or latest.app_key != binding.app_key
            or latest.auth_flow != binding.auth_flow
            or latest.status != "disconnected"
            or registry.binding_credential_is_available(binding.binding_id)
        ):
            raise
        return latest


def _mark_instagram_cleanup_pending(
    binding: MetaAssetBinding,
    *,
    restore_target: tuple[str, ...] | None,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    """Persist enough non-secret provider preimage for startup/periodic recovery."""

    error = (
        INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR if restore_target is not None else INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR
    )
    state = InstagramLoginSubscriptionState(
        status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
        subscribed_fields=tuple(restore_target or ()),
        verified_fields=tuple(restore_target or ()),
        error=error,
    )
    try:
        return cast(
            MetaAssetBinding,
            registry.update_instagram_login_webhook_subscription(
                binding.binding_id,
                state=state,
                actor_id="instagram-login-cleanup-pending",
            ),
        )
    except Exception:
        latest = next(
            (
                item
                for item in registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.webhook_subscription_status != INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
            or latest.webhook_subscription_error != error
            or latest.webhook_subscribed_fields != tuple(restore_target or ())
            or not registry.binding_credential_is_available(binding.binding_id)
        ):
            raise
        return latest


def _authorize_staged_instagram_binding_reconciled(
    *,
    registry: MetaAppRegistry,
    tenant_id: str,
    instagram_id: str,
    instagram_username: str,
    credential: MetaBindingCredential,
    actor_id: str,
) -> MetaAssetBinding:
    """Stage direct OAuth and clean a file/dual commit whose acknowledgement was lost."""

    before_ids = {
        item.binding_id
        for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        if item.tenant_id == tenant_id
        and item.channel == "instagram"
        and item.asset_id == instagram_id
        and item.app_key == APP_A_KEY
        and item.auth_flow == "instagram_login"
    }
    try:
        return registry.authorize_oauth_asset(
            tenant_id=tenant_id,
            channel="instagram",
            asset_id=instagram_id,
            page_id="",
            instagram_account_id=instagram_id,
            app_key=APP_A_KEY,
            credential=credential,
            actor_id=actor_id,
            instagram_username=instagram_username,
            status="testing",
            auth_flow="instagram_login",
            webhook_subscription_status="pending",
            create_new_binding=True,
        )
    except Exception:
        candidates = [
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id not in before_ids
            and item.tenant_id == tenant_id
            and item.channel == "instagram"
            and item.asset_id == instagram_id
            and item.app_key == APP_A_KEY
            and item.auth_flow == "instagram_login"
            and item.status == "testing"
            and registry.binding_credential_is_available(item.binding_id)
        ]
        if len(candidates) == 1:
            _discard_staged_instagram_binding_reconciled(
                candidates[0],
                actor_id=actor_id,
                registry=registry,
            )
        raise


def _instagram_activation_commit_matches(
    latest: MetaAssetBinding | None,
    *,
    staged: MetaAssetBinding,
    registry: MetaAppRegistry,
) -> bool:
    if (
        latest is None
        or not latest.active
        or latest.binding_id != staged.binding_id
        or latest.tenant_id != staged.tenant_id
        or latest.channel != "instagram"
        or latest.asset_id != staged.asset_id
        or latest.app_key != staged.app_key
        or latest.auth_flow != "instagram_login"
        or not latest.instagram_login_product_ready
        or not registry.binding_credential_is_available(latest.binding_id)
    ):
        return False
    active = [
        item
        for item in registry.list_bindings(include_inactive=False, include_superseded=True)
        if item.channel == "instagram" and item.asset_id == staged.asset_id
    ]
    return [item.binding_id for item in active] == [latest.binding_id]


async def _compensate_failed_instagram_activation(
    binding: MetaAssetBinding,
    *,
    previous_active: MetaAssetBinding | None,
    provider_preimage: tuple[str, ...] | None,
    provider_write_started: bool,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> None:
    """Restore exact provider state before archiving a failed staged credential."""

    if provider_write_started:
        actual = await inspect_instagram_login_webhook_subscription(
            binding,
            registry=registry,
            client=client,
        )
        restore_target = (
            provider_preimage
            if previous_active is not None and previous_active.auth_flow == "instagram_login"
            else None
        )
        await restore_instagram_login_webhook_subscription(
            binding,
            restore_target,
            expected_current=actual,
            registry=registry,
            client=client,
        )
    latest = next(
        (
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id == binding.binding_id
        ),
        None,
    )
    if latest is None:
        return
    if latest.active:
        raise MetaOAuthError("Instagram activation outcome is ambiguous; refusing staged cleanup")
    _discard_staged_instagram_binding_reconciled(latest, actor_id=actor_id, registry=registry)
