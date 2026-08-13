"""Resolve authenticated Meta webhook payloads to exclusive tenant/app bindings."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppConfig,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_graph_routing import build_messaging_settings_for_binding
from services.meta_instagram_login_capabilities import (
    binding_ready_for_dm,
    facebook_login_binding_superseded_for_capability,
    select_instagram_binding_for_capability,
)
from services.meta_instagram_login_config import AuthFlow, instagram_login_app_id
from services.meta_instagram_login_oauth import credential_needs_refresh
from services.meta_instagram_login_tokens import refresh_binding_instagram_login_token
from services.meta_messaging import MetaMessagingSettings, parse_meta_messaging_events


@dataclass(frozen=True)
class ResolvedMetaEvent:
    event: dict[str, Any]
    settings: MetaMessagingSettings
    binding: MetaAssetBinding


async def _prepare_binding(
    binding: MetaAssetBinding,
    *,
    app_config: MetaAppConfig,
    registry: MetaAppRegistry,
) -> tuple[MetaAssetBinding, MetaBindingCredential] | None:
    credential = registry.get_credential(binding)
    if binding.auth_flow == "facebook_login" and credential.token_app_id != app_config.app_id:
        return None
    if binding.auth_flow == "instagram_login" and credential.token_app_id != instagram_login_app_id():
        return None
    if credential.expires_at and credential.expires_at <= int(time.time()):
        registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id="webhook-token-expiry",
            expected_generation=binding.generation,
        )
        return None
    if binding.auth_flow == "instagram_login" and credential_needs_refresh(credential):
        try:
            credential = await refresh_binding_instagram_login_token(binding, registry=registry)
            binding = next(
                item for item in registry.list_bindings(include_inactive=False) if item.binding_id == binding.binding_id
            )
        except Exception:
            if credential.expires_at is not None and credential.expires_at <= int(time.time()):
                registry.set_binding_status(
                    binding.binding_id,
                    status="disconnected",
                    actor_id="webhook-token-expiry",
                    expected_generation=binding.generation,
                )
            return None
    if facebook_login_binding_superseded_for_capability(binding, "dm", registry=registry):
        return None
    if not binding_ready_for_dm(binding, credential):
        return None
    return binding, credential


def registry_auth_flow_for_webhook_object(payload_object: str) -> AuthFlow | None:
    """Auth-flow filter for signed Meta webhooks on /webhook/meta-messaging.

    Instagram object events may match an active Instagram Login binding or a
    legacy Page-linked facebook_login binding. Restricting those events to
    facebook_login drops Instagram Login DMs (parsed=0 / accepted=0).

    Page object events stay facebook_login-only. Bindings remain separate;
    the resolver still selects by tenant, asset/account ID, auth_flow, and
    active status. None means both Instagram auth flows are eligible.
    """
    return None if str(payload_object or "").strip().lower() == "instagram" else "facebook_login"


async def resolve_registry_events(
    payload: dict[str, Any],
    *,
    app_config: MetaAppConfig | None = None,
    registry: MetaAppRegistry | None = None,
    auth_flow: AuthFlow | None = None,
) -> list[ResolvedMetaEvent]:
    current_registry = registry or get_meta_app_registry()
    resolved_app = app_config or get_meta_app_configs()[APP_A_KEY]
    bindings = [
        binding
        for binding in current_registry.get_active_bindings_for_app(resolved_app.key)
        if auth_flow is None or binding.auth_flow == auth_flow
    ]
    by_message_id: dict[str, list[tuple[MetaAssetBinding, MetaBindingCredential, dict[str, Any]]]] = {}
    for binding in bindings:
        prepared = await _prepare_binding(binding, app_config=resolved_app, registry=current_registry)
        if prepared is None:
            continue
        active_binding, credential = prepared
        events = parse_meta_messaging_events(
            payload,
            instagram_account_id=active_binding.instagram_account_id or active_binding.asset_id,
            page_id=active_binding.page_id,
        )
        for event in events:
            if str(event.get("channel") or "") != active_binding.channel:
                continue
            event_account = str(event.get("account_id") or event.get("recipient_id") or "").strip()
            allowed_accounts = {active_binding.asset_id}
            if active_binding.page_id:
                allowed_accounts.add(active_binding.page_id)
            if active_binding.instagram_account_id:
                allowed_accounts.add(active_binding.instagram_account_id)
            if event_account and event_account not in allowed_accounts:
                continue
            message_id = str(event.get("message_id") or "")
            if not message_id:
                continue
            by_message_id.setdefault(message_id, []).append((active_binding, credential, event))

    resolved: list[ResolvedMetaEvent] = []
    for _message_id, options in by_message_id.items():
        instagram_options = [item for item in options if item[0].channel == "instagram"]
        facebook_options = [item for item in options if item[0].channel == "facebook"]
        chosen: tuple[MetaAssetBinding, MetaBindingCredential, dict[str, Any]] | None = None
        if instagram_options:
            selected = select_instagram_binding_for_capability(
                [binding for binding, _, _ in instagram_options],
                "dm",
                registry=current_registry,
            )
            if selected is not None:
                for binding, credential, event in instagram_options:
                    if binding.binding_id == selected.binding_id:
                        chosen = (binding, credential, event)
                        break
        elif facebook_options:
            chosen = facebook_options[0]
        if chosen is None:
            continue
        binding, credential, event = chosen
        settings = build_messaging_settings_for_binding(
            binding,
            credential=credential,
            app_config=resolved_app,
        )
        tagged = dict(event)
        tagged.update(
            {
                "tenant_id": binding.tenant_id,
                "meta_app_key": resolved_app.key,
                "meta_binding_id": binding.binding_id,
                "meta_auth_flow": binding.auth_flow,
            }
        )
        resolved.append(ResolvedMetaEvent(event=tagged, settings=settings, binding=binding))
    return resolved
