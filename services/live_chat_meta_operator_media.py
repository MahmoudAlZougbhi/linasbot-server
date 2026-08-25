"""Operator outbound media for Instagram / Facebook Live Chat threads."""

from __future__ import annotations

import base64
from typing import Any

from services.live_chat_meta_operator import parse_meta_live_chat_user_id
from services.meta_attachment_send import attachment_type_for_mime, send_stored_meta_attachment


def decode_operator_media_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


async def _build_meta_adapter_for_live_chat_user(
    *,
    tenant_id: str | None,
    user_id: str,
) -> tuple[Any, str, str]:
    from services.meta_app_registry import get_meta_app_configs, get_meta_app_registry
    from services.meta_graph_routing import build_messaging_settings_for_binding
    from services.meta_messaging import MetaMessagingAdapter, resolve_meta_send_account_id
    from services.requests.delivery import _meta_bindings_for_account

    channel, sender_id, asset_id, embedded_tenant = parse_meta_live_chat_user_id(user_id)
    tenant = str(tenant_id or embedded_tenant or "linas").strip()
    if not tenant:
        raise ValueError("tenant_required_for_meta_send")

    account = str(asset_id or "").strip()
    if not account:
        registry = get_meta_app_registry()
        bindings = [
            b
            for b in registry.list_bindings(include_inactive=False)
            if b.tenant_id == tenant and b.channel == channel and b.active
        ]
        if not bindings:
            raise ValueError("meta_binding_not_found")
        account = str(bindings[0].asset_id or "").strip()
    if not account or not sender_id:
        raise ValueError("meta_account_or_recipient_missing")

    registry = get_meta_app_registry()
    candidates = _meta_bindings_for_account(
        registry, tenant_id=tenant, account=account, meta_channels=(channel,)
    )
    if not candidates:
        raise ValueError("meta_binding_not_found")
    binding = candidates[0]
    credential = registry.get_credential(binding)
    app_config = get_meta_app_configs().get(binding.app_key)
    settings = build_messaging_settings_for_binding(binding, credential=credential, app_config=app_config)
    send_account = resolve_meta_send_account_id(
        channel,
        {"account_id": account, "recipient_id": account},
        settings,
    )
    adapter = MetaMessagingAdapter(
        access_token=settings.page_access_token,
        account_id=send_account,
        channel=channel,
        graph_api_version=settings.graph_api_version,
        graph_base_url=settings.graph_base_url,
    )
    return adapter, sender_id, channel


async def deliver_live_chat_meta_operator_media(
    *,
    tenant_id: str | None,
    user_id: str,
    media_bytes: bytes,
    mime: str,
    filename: str,
) -> dict[str, Any]:
    if not media_bytes:
        return {"success": False, "delivered": False, "error": "missing_media_bytes"}
    adapter = None
    try:
        adapter, recipient_id, channel = await _build_meta_adapter_for_live_chat_user(
            tenant_id=tenant_id,
            user_id=user_id,
        )
        att_type = attachment_type_for_mime(mime)
        if att_type == "file" and not str(mime or "").lower().startswith("application/"):
            return {
                "success": False,
                "delivered": False,
                "error": "unsupported_meta_media_type",
                "channel": channel,
            }
        result = await send_stored_meta_attachment(
            adapter,
            recipient_id=recipient_id,
            media_bytes=media_bytes,
            mime=mime,
            filename=filename,
        )
        if result.get("success") is True:
            return {
                "success": True,
                "delivered": True,
                "provider_message_id": result.get("message_id"),
                "channel": channel,
            }
        return {
            "success": False,
            "delivered": False,
            "error": str(result.get("error") or "meta_media_delivery_failed"),
            "channel": channel,
        }
    except ValueError as exc:
        return {"success": False, "delivered": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "delivered": False, "error": str(exc)[:180]}
    finally:
        if adapter is not None:
            await adapter.close()
