"""Image-quota helpers for Meta social inbound (extracted from the processor)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.meta_messaging import MetaMessagingAdapter

SendFunc = Callable[..., Awaitable[Any]]


def is_image_attachment(item: Any) -> bool:
    return bool(item) and (not isinstance(item, dict) or str(item.get("type") or "").lower() == "image")


def truncate_image_attachments(attachments: list[Any], allowed_amount: int) -> list[Any]:
    kept: list[Any] = []
    seen = 0
    limit = max(0, int(allowed_amount))
    for item in attachments:
        if is_image_attachment(item):
            if seen < limit:
                kept.append(item)
            seen += 1
        else:
            kept.append(item)
    return kept


async def deliver_image_quota_notice(
    *,
    message: str,
    user_id: str,
    sender_id: str,
    channel: str,
    binding_id: str,
    inbound_event_id: str | None,
    quota_disposition: str,
    quota_allowed_amount: int,
    adapter: MetaMessagingAdapter | None,
    capture_send: SendFunc | None,
) -> dict[str, Any] | None:
    if not message:
        return None
    if capture_send is not None:
        await capture_send(user_id, message, None, None)
        return None
    if adapter is None:
        return None
    if inbound_event_id:
        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import execute_guarded_meta_send

        result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_dm", channel=channel),
            binding_id=binding_id,
            purpose="image_quota_notice",
            image_quota_disposition=quota_disposition,
            image_quota_allowed_amount=quota_allowed_amount,
            image_quota_notice_text=message,
            send=lambda: adapter.send_text_message(sender_id, message),
        )
    else:
        result = await adapter.send_text_message(sender_id, message)

    from services.ai_reply_delivery import classify_send_result

    evidence = classify_send_result(result)
    if evidence.get("success") or evidence.get("duplicate_suppressed"):
        return None
    if evidence.get("needs_owner_action"):
        return {
            "ok": False,
            "delivery": "needs_owner_action",
            "retryable": False,
            "terminal": True,
        }
    retryable = bool(evidence.get("retryable", True))
    return {
        "ok": False,
        "delivery": "quota_notice_failed",
        "retryable": retryable,
        "terminal": not retryable,
    }
