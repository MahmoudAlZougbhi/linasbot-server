"""Clear DM/Comments CM actions when a Meta channel is disconnected."""

from __future__ import annotations

from services.channel_capability_state import (
    canonical_channel_bindings,
    comment_capability_state,
    dm_capability_state,
    supported_platforms,
)
from services.channel_capability_toggles import ChannelToggleError, set_channel_toggle

__all__ = [
    "clear_channel_toggles_after_disconnect",
    "clear_invalid_dm_enabled_state_async",
]


async def clear_channel_toggles_after_disconnect(
    *,
    tenant_id: str,
    platform: str,
    actor: str = "meta_disconnect",
) -> bool:
    """Force DM + Comments OFF when the platform has no remaining active bindings."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return False
    if canonical_channel_bindings(tenant_id, platform_key):
        return False

    dm_requested = bool(dm_capability_state(tenant_id, platform_key)["requested_enabled"])
    comments_requested = bool(comment_capability_state(tenant_id, platform_key)["requested_enabled"])
    if not dm_requested and not comments_requested:
        return False

    changed = False
    try:
        if comments_requested:
            await set_channel_toggle(
                tenant_id=tenant_id,
                platform=platform_key,
                toggle="comments",
                enabled=False,
                actor=actor,
            )
            changed = True
        if dm_requested:
            await set_channel_toggle(
                tenant_id=tenant_id,
                platform=platform_key,
                toggle="dm",
                enabled=False,
                actor=actor,
            )
            changed = True
    except ChannelToggleError:
        return False
    return changed


async def clear_invalid_dm_enabled_state_async(
    *,
    tenant_id: str,
    platform: str,
    actor: str = "dm_state_reconcile",
) -> bool:
    """Turn off CM DM when the platform is disconnected or unhealthy."""

    platform_key = (platform or "").strip().lower()
    if platform_key not in supported_platforms():
        return False
    state = dm_capability_state(tenant_id, platform_key)
    if not state["requested_enabled"]:
        return False
    if state["connection_healthy"] and canonical_channel_bindings(tenant_id, platform_key):
        return False
    try:
        await set_channel_toggle(
            tenant_id=tenant_id,
            platform=platform_key,
            toggle="dm",
            enabled=False,
            actor=actor,
        )
    except ChannelToggleError:
        return False
    return True
