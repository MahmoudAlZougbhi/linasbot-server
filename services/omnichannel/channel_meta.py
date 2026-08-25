"""Meta DM/comment provider send for the omnichannel outbox."""

from __future__ import annotations

from typing import Any

from services.omnichannel.meta_errors import MetaProviderError


async def deliver_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    surface = str(snapshot.get("surface") or "dm")
    text = str(snapshot.get("canonical_body") or "")
    if surface == "comment":
        from services.omnichannel.channel_meta_comment import deliver_meta_comment

        return await deliver_meta_comment(snapshot)

    from services.requests.delivery import deliver_meta_dm

    channel = str(snapshot.get("channel") or "instagram")
    source = "instagram_dm" if channel == "instagram" else "facebook_messenger"
    try:
        result = await deliver_meta_dm(
            tenant_id=str(snapshot["tenant_id"]),
            source_channel=source,
            source_account_id=str(snapshot.get("account_id") or ""),
            external_customer_id=str((snapshot.get("conversation_key") or "").rsplit(":", 1)[-1]),
            text=text,
        )
    except MetaProviderError as exc:
        return {
            "http_status": exc.http_status,
            "code": exc.error_code,
            "subcode": exc.error_subcode,
            "error": str(exc),
            "submitted": True,
        }
    status = str(getattr(result, "status", "") or "")
    return {
        "http_status": 200 if status == "sent" else 400,
        "message_id": str(getattr(result, "provider_message_id", "") or ""),
        "error": str(getattr(result, "error_redacted", "") or ""),
        "submitted": status in {"sent", "failed"},
    }
