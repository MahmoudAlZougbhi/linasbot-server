"""Meta OAuth Graph helpers and webhook subscribe/unsubscribe (LOC split from meta_oauth)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from services.async_safety_cleanup import await_safety_task as _await_safety_task
from services.meta_app_registry import (
    MetaAppRegistry,
    MetaAssetBinding,
    MetaRegistryError,
    get_meta_app_registry,
)
from services.meta_instagram_login_subscription import (
    inspect_instagram_login_webhook_subscription,
    instagram_channel_subscription_lock_asset,
    instagram_login_subscription_lock_asset,
    unsubscribe_instagram_login_webhook_raw,
)
from services.meta_oauth_graph_http import (  # noqa: F401 - preserve historical imports
    META_GRAPH_BASE_URL,
    MetaOAuthError,
    _debug_token,
    _graph_get,
    _graph_post_form,
    _safe_json,
)
from services.meta_oauth_graph_validation import (  # noqa: F401 - preserve historical imports
    MetaOAuthFlowMode,
    _eligible_pages,
    _granular_targets_are_allowlisted,
    _scope_tuple,
)
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation
from services.meta_page_webhook_subscription import (  # noqa: F401 - preserve historical imports
    PageWebhookSubscriptionSnapshot,
    _page_subscription_context,
    _read_page_subscription,
    _restore_binding_webhook_subscription_locked,
    desired_binding_webhook_subscription,
    inspect_binding_webhook_subscription,
    restore_binding_webhook_subscription,
    subscribe_binding_webhook,
)


def _other_active_binding_shares_page(binding: MetaAssetBinding, registry: MetaAppRegistry) -> bool:
    """True when another active binding still needs this app's Page webhook subscription."""

    page_id = str(binding.page_id or "").strip()
    if not page_id:
        return False
    for other in registry.list_bindings(include_inactive=False, include_superseded=True):
        if other.binding_id == binding.binding_id:
            continue
        if other.app_key != binding.app_key:
            continue
        if str(other.page_id or "").strip() != page_id:
            continue
        if other.auth_flow == "instagram_login":
            continue
        return True
    return False


def _other_active_direct_instagram_binding_shares_subscription(
    binding: MetaAssetBinding,
    registry: MetaAppRegistry,
) -> bool:
    """Fail safe when a newer direct binding still needs the app/account subscription."""

    for other in registry.list_bindings(include_inactive=False, include_superseded=True):
        if other.binding_id == binding.binding_id:
            continue
        if other.channel != "instagram" or other.auth_flow != "instagram_login":
            continue
        if other.app_key == binding.app_key and other.asset_id == binding.asset_id:
            return True
    return False


async def disconnect_binding_webhook(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """Mark the binding disconnected, archive its credential, and best-effort unsubscribe.

    Local routing is cut off before provider cleanup. If cleanup cannot be
    confirmed, the credential remains available only so an idempotent retry can
    finish cleanup before archival. Direct Instagram Login uses its account-scoped
    ``subscribed_apps`` endpoint; Page-linked bindings use the Page endpoint.
    """

    current_registry = registry or get_meta_app_registry()
    direct_instagram = binding.channel == "instagram" and binding.auth_flow == "instagram_login"
    lock_assets: list[str] = []
    if binding.channel == "instagram":
        lock_assets.append(instagram_channel_subscription_lock_asset(binding.tenant_id))
    provider_asset = (
        instagram_login_subscription_lock_asset(binding.asset_id)
        if direct_instagram
        else str(binding.page_id or "").strip()
    )
    if provider_asset:
        lock_assets.append(provider_asset)
    if lock_assets:
        async with lock_facebook_page_oauth_operation(
            current_registry,
            app_key=binding.app_key,
            page_ids=tuple(lock_assets),
        ):
            return await _disconnect_binding_webhook_locked(
                binding,
                actor_id=actor_id,
                registry=current_registry,
                client=client,
            )
    return await _disconnect_binding_webhook_locked(
        binding,
        actor_id=actor_id,
        registry=current_registry,
        client=client,
    )


async def _disconnect_binding_webhook_locked(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None,
) -> Any:
    """Run status -> provider cleanup -> credential archive as a retryable saga."""

    cancelled = False
    status_task = asyncio.create_task(_settle_binding_disconnect(binding, actor_id=actor_id, registry=registry))
    updated, step_cancelled, local_error = await _await_safety_task(status_task)
    cancelled = cancelled or step_cancelled
    if local_error is not None:
        if cancelled:
            raise asyncio.CancelledError
        raise local_error
    if not isinstance(updated, MetaAssetBinding):
        raise MetaRegistryError("Meta disconnect status settlement is incomplete")

    latest, credential_available = _binding_disconnect_state(updated, registry=registry)
    if latest is None or latest.status != "disconnected":
        raise MetaRegistryError("Meta disconnect status settlement is incomplete")
    if not credential_available:
        if cancelled:
            raise asyncio.CancelledError
        return latest

    provider_task = asyncio.create_task(
        _cleanup_binding_provider_subscription(latest, registry=registry, client=client)
    )
    _unused, step_cancelled, provider_error = await _await_safety_task(provider_task)
    cancelled = cancelled or step_cancelled
    if provider_error is not None:
        if cancelled or isinstance(provider_error, asyncio.CancelledError):
            raise asyncio.CancelledError
        raise provider_error

    archive_task = asyncio.create_task(
        _archive_binding_disconnect_credential(latest, actor_id=actor_id, registry=registry)
    )
    archived, step_cancelled, archive_error = await _await_safety_task(archive_task)
    cancelled = cancelled or step_cancelled
    if archive_error is not None:
        if cancelled:
            raise asyncio.CancelledError
        raise archive_error
    if cancelled:
        raise asyncio.CancelledError
    return archived


async def _cleanup_binding_provider_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None,
) -> None:
    direct_instagram = binding.channel == "instagram" and binding.auth_flow == "instagram_login"
    if direct_instagram and _other_active_direct_instagram_binding_shares_subscription(binding, registry):
        return
    if not direct_instagram:
        if not str(binding.page_id or "").strip() or _other_active_binding_shares_page(binding, registry):
            return

    owns_client = client is None
    if client is not None:
        http_client = client
    elif direct_instagram:
        http_client = httpx.AsyncClient(timeout=20.0)
    else:
        _credential, app = _page_subscription_context(binding, registry)
        http_client = httpx.AsyncClient(
            base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}",
            timeout=20.0,
        )
    try:
        if direct_instagram:
            before = await inspect_instagram_login_webhook_subscription(
                binding,
                registry=registry,
                client=http_client,
            )
            if before is None:
                return
            delete_error: BaseException | None = None
            try:
                await unsubscribe_instagram_login_webhook_raw(
                    binding,
                    registry=registry,
                    client=http_client,
                )
            except BaseException as exc:  # noqa: BLE001 - reconcile a possible lost DELETE acknowledgement
                delete_error = exc
            after = await inspect_instagram_login_webhook_subscription(
                binding,
                registry=registry,
                client=http_client,
            )
            if after is None:
                return
            if delete_error is not None:
                raise delete_error
            if after != before:
                raise MetaOAuthError("Instagram webhook subscription changed during disconnect")
            raise MetaOAuthError("Instagram webhook disconnect could not be verified")

        await _unsubscribe_binding_webhook_locked_raw(
            binding,
            registry=registry,
            client=http_client,
        )
    finally:
        if owns_client:
            await http_client.aclose()


def _binding_disconnect_state(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
) -> tuple[MetaAssetBinding | None, bool]:
    """Read exact local settlement metadata without decrypting or logging credentials."""

    latest = next(
        (
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id == binding.binding_id
        ),
        None,
    )
    if latest is None:
        return None, False
    if (
        latest.tenant_id != binding.tenant_id
        or latest.channel != binding.channel
        or latest.asset_id != binding.asset_id
        or latest.app_key != binding.app_key
        or latest.auth_flow != binding.auth_flow
    ):
        return None, False
    return latest, registry.binding_credential_is_available(latest.binding_id)


async def _settle_binding_disconnect(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
) -> Any:
    """Persist the fail-closed status, reconciling a lost commit acknowledgement."""

    latest, _credential_available = _binding_disconnect_state(binding, registry=registry)
    if latest is None:
        raise MetaRegistryError("Meta disconnect target disappeared")
    if latest.status == "disconnected":
        return latest
    try:
        return registry.set_binding_status(
            latest.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=latest.generation,
        )
    except Exception:
        committed, _credential_available = _binding_disconnect_state(binding, registry=registry)
        if committed is None or committed.status != "disconnected":
            raise
        return committed


def _disconnect_fully_settled(binding: MetaAssetBinding, *, registry: MetaAppRegistry) -> bool:
    return (
        binding.status == "disconnected"
        and not registry.binding_credential_is_available(binding.binding_id)
        and not binding.webhook_subscribed_fields
        and binding.webhook_subscription_status == "unknown"
        and not binding.webhook_subscription_error
        and binding.webhook_subscription_checked_at == 0.0
    )


async def _archive_binding_disconnect_credential(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    """Archive after provider cleanup, reconciling a lost commit acknowledgement."""

    latest, _credential_available = _binding_disconnect_state(binding, registry=registry)
    if latest is None or latest.status != "disconnected":
        raise MetaRegistryError("Meta disconnect target is not locally disconnected")
    if _disconnect_fully_settled(latest, registry=registry):
        return latest
    try:
        archived = registry.archive_binding_credential(
            latest.binding_id,
            actor_id=actor_id,
            expected_generation=latest.generation,
        )
    except Exception:
        committed, _credential_available = _binding_disconnect_state(binding, registry=registry)
        if committed is None or not _disconnect_fully_settled(committed, registry=registry):
            raise
        return committed
    if not _disconnect_fully_settled(archived, registry=registry):
        raise MetaRegistryError("Meta disconnect credential settlement is incomplete")
    return archived


async def unsubscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Delete only when no other active binding shares this app/Page row."""

    current_registry = registry or get_meta_app_registry()
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(binding.page_id,),
    ):
        if _other_active_binding_shares_page(binding, current_registry):
            return False
        await _unsubscribe_binding_webhook_locked_raw(binding, registry=current_registry, client=client)
        return True


async def _unsubscribe_binding_webhook_locked_raw(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> None:
    """DELETE and read-after-write verify after exclusive ownership is proved."""

    credential, app = _page_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        before = await _read_page_subscription(
            http_client,
            page_id=binding.page_id,
            access_token=credential.access_token,
            app_id=app.app_id,
            step="webhook disconnect preflight",
        )
        if before is None:
            return
        delete_error: BaseException | None = None
        try:
            response = await http_client.delete(
                f"{binding.page_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            payload = _safe_json(response, step="webhook disconnect")
            if payload.get("success") is not True:
                raise MetaOAuthError("Meta did not confirm the Page webhook disconnect")
        except BaseException as exc:  # noqa: BLE001 - verify a possible lost DELETE acknowledgement
            delete_error = exc
        after = await _read_page_subscription(
            http_client,
            page_id=binding.page_id,
            access_token=credential.access_token,
            app_id=app.app_id,
            step="webhook disconnect verification",
        )
        if after is None:
            return
        if delete_error is not None:
            raise delete_error
        if after != before:
            raise MetaOAuthError("Meta Page webhook subscription changed during disconnect")
        raise MetaOAuthError("Meta Page webhook disconnect could not be verified")
    finally:
        if owns_client:
            await http_client.aclose()
