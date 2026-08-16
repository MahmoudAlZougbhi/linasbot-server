"""Deliver validated product media after the text reply. No extra Tera call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.products.media import load_media_bytes, load_media_meta

SendFn = Callable[..., Awaitable[Any]]


async def send_pending_product_media(
    *,
    user_data: dict[str, Any],
    sender_id: str,
    adapter: Any | None,
    inbound_event_id: str | None,
    channel: str,
    binding_id: str,
    capture_send: SendFn | None = None,
    capture_to: str | None = None,
) -> dict[str, Any]:
    pending = user_data.get("_pending_product_media")
    if not isinstance(pending, dict) or not pending.get("ok"):
        return {"ok": True, "sent": [], "skipped": True}
    items = list(pending.get("items") or [])
    if not items:
        return {"ok": True, "sent": [], "skipped": True, "delivery_result": "no_media_items"}

    tenant_id = str(user_data.get("tenant_id") or user_data.get("tenantId") or "").strip()
    if capture_send is not None:
        sent: list[dict[str, Any]] = []
        target = capture_to or sender_id
        for item in items:
            media_id = str(item.get("media_id") or "")
            await capture_send(
                target,
                None,
                f"product-media:{media_id}",
                None,
            )
            sent.append({**item, "delivery_result": "simulated"})
        user_data["_pending_product_media"] = None
        return {
            "ok": True,
            "sent": sent,
            "ai_charged": False,
            "extra_tera_call": False,
            "delivery_result": "simulated",
        }

    if adapter is None:
        return {"ok": False, "error": "adapter_unavailable", "sent": [], "ai_charged": False}

    async def _send_all() -> dict[str, Any]:
        from services.meta_attachment_send import send_stored_product_media

        last: dict[str, Any] = {"success": False, "error": "no_items"}
        for item in items:
            media_id = str(item.get("media_id") or "").strip()
            product_id = str(item.get("product_id") or "").strip()
            if not media_id or not tenant_id:
                return {"success": False, "error": "missing_media_identity"}
            meta = load_media_meta(tenant_id=tenant_id, media_id=media_id) or {}
            if str(meta.get("tenant_id") or "") != tenant_id:
                return {"success": False, "error": "tenant_isolation"}
            raw = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
            if not raw:
                return {"success": False, "error": "media_bytes_missing", "media_id": media_id}
            last = await send_stored_product_media(
                adapter,
                recipient_id=sender_id,
                media_bytes=raw,
                mime=str(meta.get("mime") or "image/jpeg"),
                filename=str(meta.get("filename") or f"{media_id}.bin"),
                product_id=product_id,
            )
            if last.get("success") is not True:
                return last
        return last

    if inbound_event_id:
        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import execute_guarded_meta_send

        result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_dm", channel=channel),
            binding_id=binding_id,
            purpose="product_media",
            send=_send_all,
        )
    else:
        result = await _send_all()

    user_data["_pending_product_media"] = None
    from services.ai_reply_delivery import classify_send_result

    evidence = classify_send_result(result)
    delivery = "channel_sent" if evidence.get("success") or evidence.get("duplicate_suppressed") else "channel_send_failed"
    if evidence.get("duplicate_suppressed"):
        delivery = "duplicate_suppressed"
    if evidence.get("needs_owner_action"):
        delivery = "needs_owner_action"
    return {
        "ok": bool(evidence.get("success") or evidence.get("duplicate_suppressed")),
        "sent": items if delivery in {"channel_sent", "duplicate_suppressed", "simulated"} else [],
        "ai_charged": False,
        "extra_tera_call": False,
        "delivery_result": delivery,
        "provider_result": {k: result.get(k) for k in ("success", "error", "message_id", "duplicate_suppressed") if isinstance(result, dict)},
    }
