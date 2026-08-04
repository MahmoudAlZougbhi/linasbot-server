"""Resolve authenticated Meta webhook payloads to exclusive tenant/app bindings."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from services.meta_app_registry import (
    MetaAppConfig,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_registry,
)
from services.meta_messaging import MetaMessagingSettings, parse_meta_messaging_events


@dataclass(frozen=True)
class ResolvedMetaEvent:
    event: dict[str, Any]
    settings: MetaMessagingSettings
    binding: MetaAssetBinding


def resolve_registry_events(
    payload: dict[str, Any],
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry | None = None,
) -> list[ResolvedMetaEvent]:
    """Return only events owned by active bindings for the receiving app.

    A payload signed by App B cannot use an App A binding, even when the Page or
    Instagram identity appears in both apps' role/test configuration.
    """

    current_registry = registry or get_meta_app_registry()
    resolved: list[ResolvedMetaEvent] = []
    claimed: set[tuple[str, str]] = set()
    for binding in current_registry.get_active_bindings_for_app(app_config.key):
        credential = current_registry.get_credential(binding)
        if credential.token_app_id != app_config.app_id:
            continue
        if credential.expires_at and credential.expires_at <= int(time.time()):
            current_registry.set_binding_status(
                binding.binding_id,
                status="disconnected",
                actor_id="webhook-token-expiry",
                expected_generation=binding.generation,
            )
            continue
        settings = MetaMessagingSettings(
            enabled=True,
            app_secret=app_config.app_secret,
            page_id=binding.page_id,
            page_access_token=credential.access_token,
            instagram_account_id=binding.instagram_account_id,
            verify_token=app_config.verify_token,
            graph_api_version=app_config.graph_api_version,
            app_id=app_config.app_id,
            app_key=app_config.key,
            tenant_id=binding.tenant_id,
            binding_id=binding.binding_id,
        )
        events = parse_meta_messaging_events(
            payload,
            instagram_account_id=binding.instagram_account_id,
            page_id=binding.page_id,
        )
        for event in events:
            if str(event.get("channel") or "") != binding.channel:
                continue
            event_asset = binding.instagram_account_id if binding.channel == "instagram" else binding.page_id
            if event_asset != binding.asset_id:
                continue
            message_id = str(event.get("message_id") or "")
            key = (binding.binding_id, message_id)
            if key in claimed:
                continue
            claimed.add(key)
            tagged = dict(event)
            tagged.update(
                {
                    "tenant_id": binding.tenant_id,
                    "meta_app_key": app_config.key,
                    "meta_binding_id": binding.binding_id,
                }
            )
            resolved.append(ResolvedMetaEvent(event=tagged, settings=settings, binding=binding))
    return resolved
