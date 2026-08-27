"""Shared durable finalization for successful WhatsApp AI sends."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from db.models.whatsapp_cloud import WhatsAppConversation, WhatsAppMessage, WhatsAppOutboundIntent
from services.whatsapp_cloud.observability import emit_wa_event, record_analytics_channel_usage
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


def finalize_ai_outbound_sent(
    session: Session,
    *,
    repo: WhatsAppCloudRepository,
    intent: WhatsAppOutboundIntent,
    conversation: WhatsAppConversation,
    canonical_text: str,
    provider_wamid: str,
    analytics_provider_message_id: str | None = None,
) -> bool:
    """Persist one successful AI delivery and its once-only side effects.

    The intent transition, message row, timestamp, and follow-up schedule share the
    caller's transaction.  A retry that observes an already-sent intent returns
    without emitting analytics/events or scheduling a duplicate sequence.
    """

    if intent.dispatch_state == "sent":
        return False

    wamid = str(provider_wamid or "")
    text = str(canonical_text or "")
    repo.update_outbound_intent(
        intent,
        dispatch_state="sent",
        provider_wamid=wamid or None,
        error_code=None,
        error_detail=None,
    )
    repo.insert_message(
        tenant_id=intent.tenant_id,
        connection_id=intent.connection_id,
        conversation_id=intent.conversation_id,
        provider_message_id=wamid or f"local:{intent.id}",
        origin="CLOUD_API",
        direction="outbound",
        message_type="text",
        content_preview=text[:80],
        status="sent",
        meta={"source": "AI"},
    )
    conversation.last_ai_outbound_at = datetime.now(UTC)

    inbound_provider_mid = str(analytics_provider_message_id or "")
    if not inbound_provider_mid and intent.triggering_inbound_message_id:
        inbound = session.get(WhatsAppMessage, intent.triggering_inbound_message_id)
        if inbound is not None:
            inbound_provider_mid = str(inbound.provider_message_id or "")

    record_analytics_channel_usage(
        tenant_id=intent.tenant_id,
        connection_id=intent.connection_id,
        conversation_id=intent.conversation_id,
        provider_message_id=inbound_provider_mid,
        source="ai_reply",
    )
    emit_wa_event(
        "ai_reply_sent",
        connection_id=intent.connection_id,
        conversation_id=intent.conversation_id,
    )

    try:
        from services.whatsapp_cloud.smart_followup.hooks import schedule_after_ai_reply

        schedule_after_ai_reply(
            session,
            tenant_id=intent.tenant_id,
            connection_id=intent.connection_id,
            conversation_id=intent.conversation_id,
            trigger_outbound_intent_id=intent.id,
            control_epoch=int(conversation.control_epoch),
            trigger_ai_sent_at=conversation.last_ai_outbound_at,
            conversation=conversation,
        )
    except Exception as exc:
        emit_wa_event("smart_followup_schedule_failed", error=type(exc).__name__)

    return True
