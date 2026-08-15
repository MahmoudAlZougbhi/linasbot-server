"""Channel-scoped Meta disconnect helpers.

Disconnect operates on an explicit binding set and never broadens from Instagram
to its linked Facebook Page (or vice versa).  Historical inactive/testing
siblings are credential-archived so a platform disconnect cannot leave a hidden
authorization that later becomes routable again.
"""

from __future__ import annotations

from collections.abc import Iterable

from services.meta_app_registry import MetaAppRegistry, MetaAssetBinding, MetaRegistryError
from services.meta_instagram_login_subscription import (
    instagram_channel_subscription_lock_asset,
    instagram_login_subscription_lock_asset,
)
from services.meta_oauth import disconnect_binding_webhook
from services.meta_oauth_graph_http import MetaOAuthError
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation


async def disconnect_meta_binding_set(
    bindings: Iterable[MetaAssetBinding],
    *,
    actor_id: str,
    registry: MetaAppRegistry,
    asset_id: str | None = None,
) -> tuple[MetaAssetBinding, ...]:
    targets = tuple(bindings)
    if not targets:
        return ()
    tenants = {item.tenant_id for item in targets}
    channels = {item.channel for item in targets}
    if len(tenants) != 1 or len(channels) != 1:
        raise MetaRegistryError("Meta disconnect target set crosses tenant or channel boundary")
    resolved_asset = None if asset_id is None else str(asset_id or "").strip()
    if asset_id is not None and (not resolved_asset or any(item.asset_id != resolved_asset for item in targets)):
        raise MetaRegistryError("Meta disconnect target set crosses asset boundary")

    lock_assets: set[str] = set()
    channel = next(iter(channels))
    tenant = next(iter(tenants))
    if channel == "instagram":
        # This tenant/channel fence is also taken by every direct Instagram
        # connect.  Once held, the exact target set below cannot gain a new
        # routable direct binding between its status cut-off and cleanup.
        lock_assets.add(instagram_channel_subscription_lock_asset(tenant))
    for target in targets:
        if target.channel == "instagram" and target.auth_flow == "instagram_login":
            lock_assets.add(instagram_login_subscription_lock_asset(target.asset_id))
        else:
            page_id = str(target.page_id or "").strip()
            if page_id:
                lock_assets.add(page_id)
    if lock_assets:
        async with lock_facebook_page_oauth_operation(
            registry,
            app_key=targets[0].app_key,
            page_ids=tuple(sorted(lock_assets)),
        ):
            return await _disconnect_meta_binding_set_locked(
                targets,
                actor_id=actor_id,
                registry=registry,
                asset_id=resolved_asset,
            )
    return await _disconnect_meta_binding_set_locked(
        targets,
        actor_id=actor_id,
        registry=registry,
        asset_id=resolved_asset,
    )


async def _disconnect_meta_binding_set_locked(
    targets: tuple[MetaAssetBinding, ...],
    *,
    actor_id: str,
    registry: MetaAppRegistry,
    asset_id: str | None,
) -> tuple[MetaAssetBinding, ...]:
    """Re-read a closed scope, cut all routing, then settle provider state."""

    tenants = {item.tenant_id for item in targets}
    channels = {item.channel for item in targets}
    if len(tenants) != 1 or len(channels) != 1:
        raise MetaRegistryError("Meta disconnect target set crosses tenant or channel boundary")
    resolved_asset = None if asset_id is None else str(asset_id or "").strip()
    if asset_id is not None and (not resolved_asset or any(item.asset_id != resolved_asset for item in targets)):
        raise MetaRegistryError("Meta disconnect target set crosses asset boundary")

    for target in targets:
        latest = next(
            (
                item
                for item in registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == target.binding_id
            ),
            None,
        )
        if latest is None:
            raise MetaRegistryError("Meta disconnect target disappeared")
        if (
            latest.tenant_id not in tenants
            or latest.channel not in channels
            or (resolved_asset is not None and latest.asset_id != resolved_asset)
        ):
            raise MetaRegistryError("Meta disconnect target changed ownership scope")

    tenant = next(iter(tenants))
    channel = next(iter(channels))
    try:
        status_targets = registry.disconnect_binding_statuses(
            tuple(item.binding_id for item in targets),
            tenant_id=tenant,
            channel=channel,
            asset_id=resolved_asset,
            actor_id=actor_id,
        )
    except Exception:
        scope_rows = [
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.tenant_id == tenant
            and item.channel == channel
            and (resolved_asset is None or item.asset_id == resolved_asset)
        ]
        by_id = {item.binding_id: item for item in scope_rows}
        target_ids = {item.binding_id for item in targets}
        reconciled = [by_id.get(item.binding_id) for item in targets]
        extra_unsettled = [
            item
            for item in scope_rows
            if item.binding_id not in target_ids
            and (item.status != "disconnected" or registry.binding_credential_is_available(item.binding_id))
        ]
        if any(item is None or item.status != "disconnected" for item in reconciled) or extra_unsettled:
            raise
        status_targets = tuple(item for item in reconciled if item is not None)

    for latest in status_targets:
        if registry.binding_credential_is_available(latest.binding_id):
            try:
                await disconnect_binding_webhook(
                    latest,
                    actor_id=actor_id,
                    registry=registry,
                )
            except (MetaOAuthError, MetaRegistryError):
                # Owner intent already won atomically for the full channel scope.
                # Keep the encrypted credential only for the fair periodic
                # provider-cleanup retry; never reactivate routing here.
                continue

    latest_rows = registry.list_bindings(include_inactive=True, include_superseded=True)
    latest_by_id = {item.binding_id: item for item in latest_rows}
    if any(latest_by_id.get(item.binding_id) is None for item in targets):
        raise MetaRegistryError("Meta disconnect settlement is incomplete")
    if any(latest_by_id[item.binding_id].status != "disconnected" for item in targets):
        raise MetaRegistryError("Meta disconnect settlement is incomplete")
    remaining = [
        item
        for item in latest_rows
        if item.tenant_id == tenant
        and item.channel == channel
        and item.status != "disconnected"
        and (resolved_asset is None or item.asset_id == resolved_asset)
    ]
    if remaining:
        raise MetaRegistryError("Meta disconnect scope changed; retry required")
    return tuple(latest_by_id[item.binding_id] for item in targets)
