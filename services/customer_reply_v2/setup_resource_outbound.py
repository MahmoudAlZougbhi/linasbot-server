"""Deliver validated AI Setup resources after the text reply. No extra Tera call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.cm.article_media import load_media_bytes, load_media_meta
from services.cm.setup_resources import resolve_published_resource

SendFn = Callable[..., Awaitable[Any]]


def _whatsapp_policy_blocked(channel: str) -> dict[str, Any] | None:
    ch = str(channel or "").strip().lower()
    if "whatsapp" not in ch:
        return None
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    flags = get_whatsapp_cloud_flags()
    if flags.public_availability and flags.outbound_sends_enabled:
        return None
    return {
        "ok": False,
        "error": "whatsapp_disabled_by_product_policy",
        "sent": [],
        "ai_charged": False,
        "claimed_sent": False,
        "delivery_result": "DISABLED BY PRODUCT POLICY",
    }


async def send_pending_setup_resources(
    *,
    user_data: dict[str, Any],
    sender_id: str,
    adapter: Any | None,
    inbound_event_id: str | None,
    channel: str,
    binding_id: str,
    capture_send: SendFn | None = None,
    capture_to: str | None = None,
    purpose: str = "ai_setup_resource",
    pending_key: str = "_pending_setup_resources",
    recipient_field: str = "id",
) -> dict[str, Any]:
    blocked = _whatsapp_policy_blocked(channel)
    if blocked is not None:
        return blocked
    pending = user_data.get(pending_key)
    if not isinstance(pending, dict) or not pending.get("ok"):
        return {"ok": True, "sent": [], "skipped": True, "claimed_sent": False}
    items = list(pending.get("items") or [])
    if not items:
        return {"ok": True, "sent": [], "skipped": True, "delivery_result": "no_resource_items", "claimed_sent": False}

    tenant_id = str(user_data.get("tenant_id") or user_data.get("tenantId") or "").strip()
    if capture_send is not None:
        sent: list[dict[str, Any]] = []
        target = capture_to or sender_id
        for item in items:
            ref = str(item.get("resource_ref") or "")
            kind = str(item.get("resource_type") or "file")
            caption = str(item.get("title") or ref) if kind == "link" else None
            await capture_send(target, caption, f"setup-resource:{ref}", None)
            sent.append({**item, "delivery_result": "simulated"})
        user_data[pending_key] = None
        return {
            "ok": True,
            "sent": sent,
            "ai_charged": False,
            "extra_tera_call": False,
            "delivery_result": "simulated",
            "claimed_sent": False,
        }

    if adapter is None:
        return {"ok": False, "error": "adapter_unavailable", "sent": [], "ai_charged": False, "claimed_sent": False}

    async def _send_all() -> dict[str, Any]:
        from services.meta_attachment_send import send_stored_meta_attachment

        last: dict[str, Any] = {"success": False, "error": "no_items"}
        for item in items:
            ref = str(item.get("resource_ref") or "").strip()
            hit = resolve_published_resource(tenant_id=tenant_id, resource_ref=ref)
            if not hit.get("ok"):
                return {"success": False, "error": str(hit.get("error") or "resource_not_found"), "resource_ref": ref}
            record = dict(hit.get("resource") or {})
            if str(record.get("tenant_id") or "") != tenant_id:
                return {"success": False, "error": "tenant_isolation"}
            kind = str(record.get("resource_type") or "file")
            if kind == "link":
                url = str(record.get("external_url") or "").strip()
                if not url:
                    return {"success": False, "error": "link_url_missing", "resource_ref": ref}
                last = await adapter.send_text_message(sender_id, url)
                if last.get("success") is not True:
                    return last
                continue
            media_id = str(record.get("storage_key") or ref)
            meta = load_media_meta(tenant_id=tenant_id, media_id=media_id) or {}
            if str(meta.get("tenant_id") or "") != tenant_id:
                return {"success": False, "error": "tenant_isolation"}
            raw = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
            if not raw:
                return {"success": False, "error": "media_bytes_missing", "resource_ref": ref}
            last = await send_stored_meta_attachment(
                adapter,
                recipient_id=sender_id,
                media_bytes=raw,
                mime=str(meta.get("mime") or record.get("mime_type") or "application/octet-stream"),
                filename=str(meta.get("filename") or f"{media_id}.bin"),
                recipient_field=recipient_field,
            )
            if last.get("success") is not True:
                return last
        return last

    from services.customer_reply_v2.channel_metadata import parse_channel

    platform, surface, _is_public = parse_channel(channel)
    kind = "meta_comment" if surface == "comment" or recipient_field == "comment_id" else "meta_dm"
    if inbound_event_id:
        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import execute_guarded_meta_send

        result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind=kind, channel=platform),
            binding_id=binding_id,
            purpose=purpose,  # type: ignore[arg-type]
            send=_send_all,
        )
    else:
        result = await _send_all()

    user_data[pending_key] = None
    from services.ai_reply_delivery import classify_send_result

    evidence = classify_send_result(result)
    delivery = (
        "channel_sent" if evidence.get("success") or evidence.get("duplicate_suppressed") else "channel_send_failed"
    )
    if evidence.get("duplicate_suppressed"):
        delivery = "duplicate_suppressed"
    if evidence.get("needs_owner_action"):
        delivery = "needs_owner_action"
    claimed = delivery in {"channel_sent", "duplicate_suppressed"}
    return {
        "ok": bool(claimed),
        "sent": items if claimed or delivery == "simulated" else [],
        "ai_charged": False,
        "extra_tera_call": False,
        "delivery_result": delivery,
        "claimed_sent": claimed,
        "provider_result": {
            k: result.get(k)
            for k in ("success", "error", "message_id", "duplicate_suppressed")
            if isinstance(result, dict)
        },
    }
