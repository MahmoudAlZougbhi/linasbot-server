"""Compose tenant-isolated social user IDs for Meta Messenger and Instagram."""

from __future__ import annotations

from services.meta_app_registry import MetaChannel, get_meta_app_registry, normalize_meta_tenant_id


def tenant_channel_has_multiple_active_assets(tenant_id: str, channel: MetaChannel) -> bool:
    tenant = normalize_meta_tenant_id(tenant_id)
    matches = [
        binding
        for binding in get_meta_app_registry().list_bindings(include_inactive=False, include_superseded=False)
        if binding.tenant_id == tenant and binding.channel == channel
    ]
    return len(matches) > 1


def compose_social_user_id(
    *,
    tenant_id: str,
    channel: str,
    asset_id: str,
    sender_id: str,
    multi_asset_channel: bool | None = None,
) -> str:
    tenant = normalize_meta_tenant_id(tenant_id)
    channel_name = str(channel or "").strip().lower()
    asset = str(asset_id or "").strip()
    sender = str(sender_id or "").strip()
    scoped = multi_asset_channel
    if scoped is None:
        scoped = tenant_channel_has_multiple_active_assets(tenant, channel_name)  # type: ignore[arg-type]
    if tenant == "linas" and not scoped:
        return f"{channel_name}:{sender}"
    if tenant == "linas":
        return f"{channel_name}:{asset}:{sender}"
    return f"{tenant}:{channel_name}:{asset}:{sender}"
