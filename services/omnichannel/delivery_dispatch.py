"""Dispatch persisted canonical replies. Retries never regenerate AI."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob


async def deliver_outbox_row(job: QueueJob) -> dict[str, Any]:
    payload = job.payload or {}
    if payload.get("regenerate_ai"):
        raise PermissionError("delivery_retry_must_reuse_canonical_reply")
    body = str(payload.get("canonical_body") or "")
    if not body:
        return {"ok": False, "reason": "missing_canonical_body"}
    channel = str(payload.get("channel") or "")
    if channel in {"instagram", "facebook"}:
        from services.requests.delivery import deliver_meta_dm

        result = await deliver_meta_dm(
            tenant_id=job.tenant_id,
            source_channel=str(payload.get("source_channel") or "instagram_dm"),
            source_account_id=str(payload.get("account_id") or "") or None,
            external_customer_id=str(payload.get("recipient_id") or ""),
            text=body,
        )
        return {"ok": result.status == "sent", "channel": channel, "status": result.status}
    if channel == "whatsapp":
        from services.whatsapp_cloud.delivery_retry import send_canonical_intent

        return await send_canonical_intent(str(payload.get("intent_id") or ""))
    if channel == "tiktok":
        return {"ok": False, "reason": "tiktok_dm_permission_pending", "gated": True}
    return {"ok": False, "reason": f"unsupported_channel:{channel}"}
