"""Schedule Smart Follow-Up after website chat AI replies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT
from services.web_chat.flags import web_chat_containment_active


def maybe_schedule_web_followup_after_ai_reply(
    *,
    tenant_id: str,
    user_id: str,
    visitor_session_id: str,
    conversation_id: str,
    widget_key: str,
    trigger_ref: str | None = None,
) -> dict[str, Any] | None:
    tid = str(tenant_id or "").strip()
    vid = str(visitor_session_id or "").strip()
    if not tid or not vid or not conversation_id:
        return None
    if web_chat_containment_active():
        return {"scheduled": False, "reason": "web_chat_contained"}

    from db.session import whatsapp_session
    from services.smart_followup.hooks import schedule_after_ai_reply

    sent_at = datetime.now(UTC)
    channel_context = {
        "user_id": user_id,
        "profile_name": "Website visitor",
        "social_sender_id": vid,
        "asset_id": widget_key,
        "meta_binding_id": widget_key,
        "trigger_ref": trigger_ref or f"web:{conversation_id}:{int(sent_at.timestamp())}",
        "last_inbound_at": sent_at.isoformat(),
    }
    try:
        with whatsapp_session() as session:
            return schedule_after_ai_reply(
                session,
                tenant_id=tid,
                channel=SOURCE_CHANNEL_WEB_CHAT,
                connection_id=widget_key,
                conversation_id=conversation_id,
                trigger_outbound_intent_id=channel_context["trigger_ref"],
                control_epoch=1,
                trigger_ai_sent_at=sent_at,
                channel_context=channel_context,
            )
    except Exception as exc:
        from services.whatsapp_cloud.observability import emit_wa_event

        emit_wa_event("smart_followup_schedule_failed", error=type(exc).__name__, channel=SOURCE_CHANNEL_WEB_CHAT)
        return {"scheduled": False, "reason": "schedule_failed"}
