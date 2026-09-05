"""Channel delivery for Customer Requests notifications (original channel only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.requests.constants import (
    SOURCE_CHANNEL_COMMENT_LINKED_DM,
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)

DeliveryStatus = Literal["sent", "failed", "blocked"]

# Meta / WhatsApp codes that mean the platform permanently blocked delivery.
_META_BLOCKED_CODES = frozenset({10, 200, 551, 100})
_WA_BLOCKED_CODES = frozenset({"131026", "131047", "131051", "130472", "meta_131026", "meta_131047"})


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    error_redacted: str | None = None
    provider_message_id: str | None = None
    channel_used: str | None = None


def redact_delivery_error(exc: BaseException | str, *, limit: int = 480) -> str:
    text = str(exc or "delivery_failed")
    # Strip token-like material.
    lowered = text.lower()
    for needle in ("bearer ", "access_token", "page_access_token", "authorization:"):
        if needle in lowered:
            return "delivery_failed:credential_or_auth_error"
    return text[:limit]


def classify_platform_block(*, channel: str, error_code: str | int | None, message: str) -> bool:
    code_s = str(error_code or "").strip()
    code_i: int | None = None
    try:
        code_i = int(code_s) if code_s.isdigit() else None
    except ValueError:
        code_i = None
    ch = (channel or "").strip().lower()
    if ch == SOURCE_CHANNEL_WHATSAPP_CLOUD:
        if code_s in _WA_BLOCKED_CODES or (code_i is not None and str(code_i) in _WA_BLOCKED_CODES):
            return True
        if "user is part of an experiment" in (message or "").lower():
            return True
        return False
    if code_i in _META_BLOCKED_CODES:
        return True
    msg = (message or "").lower()
    return "blocked" in msg or "cannot message" in msg or "not allowed to message" in msg


def _meta_channel_for_source(source_channel: str) -> str:
    if source_channel == SOURCE_CHANNEL_FACEBOOK_MESSENGER:
        return "facebook"
    return "instagram"


def _meta_bindings_for_account(
    registry: Any,
    *,
    tenant_id: str,
    account: str,
    meta_channels: tuple[str, ...],
) -> list[Any]:
    """Match active tenant bindings by asset/page/IG id within allowed Meta channels."""
    bindings = registry.list_bindings(include_inactive=False)
    exact = [
        b
        for b in bindings
        if b.tenant_id == tenant_id and b.channel in meta_channels and b.asset_id == account and b.active
    ]
    if exact:
        return exact
    return [
        b
        for b in bindings
        if b.tenant_id == tenant_id
        and b.channel in meta_channels
        and account in {b.asset_id, b.page_id, b.instagram_account_id}
        and b.active
    ]


async def deliver_whatsapp_cloud(
    *,
    tenant_id: str,
    conversation_id: str | None,
    recipient_wa_id: str | None,
    text: str,
    session: Any,
) -> DeliveryResult:
    from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    if not text.strip():
        return DeliveryResult(
            status="failed", error_redacted="empty_message", channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD
        )
    repo = WhatsAppCloudRepository(session)
    conv = None
    if conversation_id:
        conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
    if conv is None and recipient_wa_id:
        return DeliveryResult(
            status="failed",
            error_redacted="whatsapp_conversation_required",
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )
    if conv is None or conv.tenant_id != tenant_id:
        return DeliveryResult(
            status="failed",
            error_redacted="conversation_not_found",
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )
    conn = repo.get_connection(conv.connection_id)
    if conn is None or conn.tenant_id != tenant_id:
        return DeliveryResult(
            status="failed",
            error_redacted="connection_not_found",
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )
    try:
        token = repo.load_access_token(conn)
        result = await send_text_message(
            access_token=token,
            phone_number_id=conn.phone_number_id,
            to_wa_id=conv.customer_wa_id,
            text=text.strip(),
        )
        mid = None
        messages = result.get("messages") if isinstance(result, dict) else None
        if isinstance(messages, list) and messages:
            mid = str((messages[0] or {}).get("id") or "") or None
        return DeliveryResult(
            status="sent",
            provider_message_id=mid,
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )
    except WhatsAppGraphError as exc:
        blocked = classify_platform_block(
            channel=SOURCE_CHANNEL_WHATSAPP_CLOUD, error_code=exc.code, message=exc.message
        )
        return DeliveryResult(
            status="blocked" if blocked else "failed",
            error_redacted=redact_delivery_error(f"{exc.code}:{exc.message}"),
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )
    except Exception as exc:
        return DeliveryResult(
            status="failed",
            error_redacted=redact_delivery_error(exc),
            channel_used=SOURCE_CHANNEL_WHATSAPP_CLOUD,
        )


async def deliver_meta_dm(
    *,
    tenant_id: str,
    source_channel: str,
    source_account_id: str | None,
    external_customer_id: str | None,
    text: str,
) -> DeliveryResult:
    from services.meta_app_registry import get_meta_app_configs, get_meta_app_registry
    from services.meta_graph_routing import build_messaging_settings_for_binding
    from services.meta_messaging import MetaMessagingAdapter, resolve_meta_send_account_id

    if not text.strip():
        return DeliveryResult(status="failed", error_redacted="empty_message", channel_used=source_channel)
    recipient = str(external_customer_id or "").strip()
    account = str(source_account_id or "").strip()
    if not recipient or not account:
        return DeliveryResult(
            status="failed",
            error_redacted="missing_recipient_or_account",
            channel_used=source_channel,
        )

    registry = get_meta_app_registry()
    if source_channel == SOURCE_CHANNEL_COMMENT_LINKED_DM:
        # Resolve IG vs FB from tenant bindings by asset — never WhatsApp / never invent channel.
        meta_channels: tuple[str, ...] = ("instagram", "facebook")
        candidates = _meta_bindings_for_account(
            registry, tenant_id=tenant_id, account=account, meta_channels=meta_channels
        )
    else:
        meta_channel = _meta_channel_for_source(source_channel)
        candidates = _meta_bindings_for_account(
            registry, tenant_id=tenant_id, account=account, meta_channels=(meta_channel,)
        )
    if not candidates:
        return DeliveryResult(
            status="failed",
            error_redacted="binding_not_found",
            channel_used=source_channel,
        )
    from services.meta_dm_binding_select import select_binding_for_meta_dm

    binding = select_binding_for_meta_dm(
        candidates,
        channel=str(candidates[0].channel),
        registry=registry,
    )
    if binding is None:
        return DeliveryResult(
            status="failed",
            error_redacted="binding_not_found",
            channel_used=source_channel,
        )
    meta_channel = str(binding.channel)
    credential = registry.get_credential(binding)
    app_config = get_meta_app_configs().get(binding.app_key)
    settings = build_messaging_settings_for_binding(binding, credential=credential, app_config=app_config)
    send_account = resolve_meta_send_account_id(
        meta_channel,
        {"account_id": account, "recipient_id": account},
        settings,
    )
    adapter = MetaMessagingAdapter(
        access_token=settings.page_access_token,
        account_id=send_account,
        channel=meta_channel,
        graph_api_version=settings.graph_api_version,
        graph_base_url=settings.graph_base_url,
    )
    try:
        result = await adapter.send_text_message(recipient, text.strip())
        mid = None
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, list) and data:
            mid = str((data[0] or {}).get("message_id") or (data[0] or {}).get("id") or "") or None
        return DeliveryResult(status="sent", provider_message_id=mid, channel_used=source_channel)
    except Exception as exc:
        msg = redact_delivery_error(exc)
        blocked = classify_platform_block(channel=source_channel, error_code=None, message=msg)
        # Parse code=N from MetaMessagingAdapter RuntimeError if present.
        if "code=" in str(exc):
            try:
                part = str(exc).split("code=", 1)[1].split()[0]
                blocked = classify_platform_block(channel=source_channel, error_code=part, message=msg)
            except Exception:
                pass
        return DeliveryResult(
            status="blocked" if blocked else "failed",
            error_redacted=msg,
            channel_used=source_channel,
        )
    finally:
        await adapter.close()


async def deliver_on_source_channel(
    *,
    tenant_id: str,
    channel: str,
    source_account_id: str | None,
    external_customer_id: str | None,
    conversation_id: str | None,
    text: str,
    session: Any = None,
) -> DeliveryResult:
    """Send on the request's original channel only — never silently switch providers."""
    ch = (channel or "").strip().lower()
    if ch == SOURCE_CHANNEL_WHATSAPP_CLOUD:
        if session is None:
            return DeliveryResult(status="failed", error_redacted="session_required", channel_used=ch)
        return await deliver_whatsapp_cloud(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            recipient_wa_id=external_customer_id,
            text=text,
            session=session,
        )
    if ch in {
        SOURCE_CHANNEL_INSTAGRAM_DM,
        SOURCE_CHANNEL_FACEBOOK_MESSENGER,
        SOURCE_CHANNEL_COMMENT_LINKED_DM,
    }:
        # comment_linked_dm: Meta DM via asset binding (IG or FB) — never WhatsApp.
        result = await deliver_meta_dm(
            tenant_id=tenant_id,
            source_channel=ch,
            source_account_id=source_account_id,
            external_customer_id=external_customer_id,
            text=text,
        )
        # Preserve original outbox channel label (no silent channel switch in records).
        return DeliveryResult(
            status=result.status,
            error_redacted=result.error_redacted,
            provider_message_id=result.provider_message_id,
            channel_used=ch,
        )
    return DeliveryResult(status="failed", error_redacted=f"unsupported_channel:{ch}", channel_used=ch)
