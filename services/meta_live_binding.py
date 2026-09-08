"""Re-resolve the current active Meta binding for outbound send.

Signature validation and payload routing stay elsewhere. This module only
follows tenant + platform + account identity so a reconnect cannot revive a
superseded token or cross Facebook and Instagram credentials.
"""

from __future__ import annotations

import logging
from typing import Any

from services.meta_app_registry import MetaAssetBinding
from services.queues.handlers import PermanentJobError

_runtime_logger = logging.getLogger("uvicorn.error")


def _same_binding_identity(left: MetaAssetBinding, right: MetaAssetBinding) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.channel == right.channel
        and left.asset_id == right.asset_id
        and left.app_key == right.app_key
        and left.auth_flow == right.auth_flow
    )


def _required_auth_flow(*, channel: str, snapshot_auth_flow: str) -> str:
    channel_name = str(channel or "").strip().lower()
    flow = str(snapshot_auth_flow or "").strip().lower()
    if channel_name == "instagram":
        return "instagram_login"
    if channel_name == "facebook":
        return "facebook_login"
    return flow or "facebook_login"


def _unique_active_for_identity(
    bindings: list[MetaAssetBinding],
    *,
    tenant_id: str,
    channel: str,
    asset_id: str,
    auth_flow: str,
) -> MetaAssetBinding | None:
    matches = [
        item
        for item in bindings
        if item.active
        and item.tenant_id == tenant_id
        and item.channel == channel
        and item.asset_id == asset_id
        and item.auth_flow == auth_flow
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_live_outbound_binding(
    data: dict[str, Any],
    binding_data: dict[str, Any],
) -> MetaAssetBinding:
    """Follow a replacement chain, then the unique live binding for the same asset."""

    from services.meta_app_registry import get_meta_app_registry

    binding_id = str(binding_data.get("binding_id") or data.get("binding_id") or "").strip()
    if not binding_id or binding_id == "legacy-single-app":
        raise PermanentJobError("meta binding identifier is unavailable")
    registry = get_meta_app_registry()
    all_bindings = registry.list_bindings(include_inactive=True, include_superseded=True)
    original = next((item for item in all_bindings if item.binding_id == binding_id), None)
    if original is None:
        live = _unique_active_for_identity(
            all_bindings,
            tenant_id=str(binding_data.get("tenant_id") or data.get("tenant_id") or "").strip(),
            channel=str(binding_data.get("channel") or data.get("channel") or "").strip().lower(),
            asset_id=str(binding_data.get("asset_id") or "").strip(),
            auth_flow=_required_auth_flow(
                channel=str(binding_data.get("channel") or data.get("channel") or ""),
                snapshot_auth_flow=str(binding_data.get("auth_flow") or data.get("auth_flow") or ""),
            ),
        )
        if live is None:
            raise PermanentJobError("meta binding is unavailable")
        _runtime_logger.info(
            "[meta-binding] re_resolved_missing_snapshot snapshot=%s live=%s auth_flow=%s",
            binding_id[:12],
            live.binding_id[:12],
            live.auth_flow,
        )
        return live

    tenant_id = str(binding_data.get("tenant_id") or data.get("tenant_id") or original.tenant_id or "").strip()
    channel = str(binding_data.get("channel") or data.get("channel") or original.channel or "").strip().lower()
    asset_id = str(binding_data.get("asset_id") or original.asset_id or "").strip()
    app_key = str(binding_data.get("app_key") or data.get("app_key") or original.app_key or "").strip()
    snapshot_flow = str(binding_data.get("auth_flow") or data.get("auth_flow") or original.auth_flow or "").strip()
    required_flow = _required_auth_flow(channel=channel, snapshot_auth_flow=snapshot_flow)
    if not tenant_id or not channel or not asset_id or not app_key:
        raise PermanentJobError("meta binding snapshot identity is invalid")
    if original.tenant_id != tenant_id or original.channel != channel or original.asset_id != asset_id:
        raise PermanentJobError("meta binding snapshot identity is invalid")
    if original.app_key != app_key:
        raise PermanentJobError("meta binding snapshot identity is invalid")
    if required_flow == "instagram_login" and original.auth_flow == "facebook_login":
        live = _unique_active_for_identity(
            all_bindings,
            tenant_id=tenant_id,
            channel="instagram",
            asset_id=asset_id,
            auth_flow="instagram_login",
        )
        if live is None:
            _runtime_logger.warning(
                "[meta-binding] no_active_instagram_login tenant=%s asset=%s snapshot=%s",
                tenant_id,
                asset_id,
                binding_id[:12],
            )
            raise PermanentJobError("no_active_instagram_login")
        _runtime_logger.info(
            "[meta-binding] re_resolved_from_superseded_facebook snapshot=%s live=%s auth_flow=%s",
            binding_id[:12],
            live.binding_id[:12],
            live.auth_flow,
        )
        return live

    by_id = {item.binding_id: item for item in all_bindings if _same_binding_identity(item, original)}
    connected: dict[str, MetaAssetBinding] = {}
    pending = [original]
    while pending:
        current = pending.pop()
        if current.binding_id in connected:
            continue
        connected[current.binding_id] = current
        if current.previous_binding_id and current.previous_binding_id in by_id:
            pending.append(by_id[current.previous_binding_id])
        pending.extend(
            item
            for item in by_id.values()
            if item.previous_binding_id == current.binding_id and item.binding_id not in connected
        )
    active = [item for item in connected.values() if item.active]
    if len(active) == 1:
        if active[0].binding_id != binding_id:
            _runtime_logger.info(
                "[meta-binding] re_resolved_chain snapshot=%s live=%s status=%s auth_flow=%s",
                binding_id[:12],
                active[0].binding_id[:12],
                active[0].status,
                active[0].auth_flow,
            )
        return active[0]

    live = _unique_active_for_identity(
        all_bindings,
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id,
        auth_flow=required_flow,
    )
    if live is None:
        _runtime_logger.warning(
            "[meta-binding] no_unique_active_replacement tenant=%s channel=%s asset=%s flow=%s snapshot=%s",
            tenant_id,
            channel,
            asset_id,
            required_flow,
            binding_id[:12],
        )
        raise PermanentJobError("meta binding has no unique active replacement")
    if live.auth_flow != required_flow:
        raise PermanentJobError("meta binding auth_flow isolation violated")
    _runtime_logger.info(
        "[meta-binding] re_resolved_live snapshot=%s live=%s auth_flow=%s",
        binding_id[:12],
        live.binding_id[:12],
        live.auth_flow,
    )
    return live
