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

    _settle_confirmed_send(
        tenant_id=intent.tenant_id,
        inbound_mid=inbound_provider_mid,
        provider_wamid=wamid,
        triggering_inbound_id=str(intent.triggering_inbound_message_id or ""),
        conversation_id=str(intent.conversation_id or ""),
        intent_mid=inbound_mid_from_intent(intent),
    )
    return True


def _settle_confirmed_send(
    *,
    tenant_id: str,
    inbound_mid: str,
    provider_wamid: str,
    triggering_inbound_id: str,
    conversation_id: str = "",
    intent_mid: str = "",
) -> None:
    request_id = f"wa:{inbound_mid or intent_mid}" if (inbound_mid or intent_mid) else ""
    reservation_id = ""
    if request_id:
        try:
            from services.credit_ledger_service import credit_ledger_service

            reservation_id = credit_ledger_service.find_open_reservation_by_request(tenant_id, request_id) or ""
        except Exception:
            reservation_id = ""
    if reservation_id:
        from services.customer_ai.leftover_reserve import capture_leftover_reply

        capture_leftover_reply(
            tenant_id,
            reservation_id,
            model_provider="whatsapp_cloud",
            operation_id=request_id,
            provider_message_id=provider_wamid,
        )
    from services.customer_ai.billing import settle_after_send

    settle_after_send(
        tenant_id=tenant_id,
        operation_id=inbound_mid or intent_mid or triggering_inbound_id,
        accepted=True,
        channel="whatsapp_cloud",
        provider_message_id=provider_wamid,
        extra_ids=(request_id, reservation_id, triggering_inbound_id, intent_mid, conversation_id),
    )


def inbound_mid_from_intent(intent: WhatsAppOutboundIntent) -> str:
    key = str(getattr(intent, "idempotency_key", "") or "")
    if key.startswith("ai:"):
        return key[3:].strip()
    return ""


def release_unsent_ai_outbound(
    *,
    tenant_id: str,
    inbound_mid: str = "",
    inbound_id: str = "",
    reservation_id: str | None = None,
    conversation_id: str = "",
    intent_mid: str = "",
) -> None:
    """Release leftover credits and message units when the send was never submitted."""
    rid = str(reservation_id or "")
    mid = inbound_mid or intent_mid
    if not rid and mid:
        try:
            from services.credit_ledger_service import credit_ledger_service

            rid = credit_ledger_service.find_open_reservation_by_request(tenant_id, f"wa:{mid}") or ""
        except Exception:
            rid = ""
    if rid:
        try:
            from services.customer_ai.leftover_reserve import release_leftover_reply

            release_leftover_reply(tenant_id, rid)
        except Exception:
            emit_wa_event("credit_release_failed", tenant_id=tenant_id)
    from services.customer_ai.billing import settle_after_send

    settle_after_send(
        tenant_id=tenant_id,
        operation_id=mid or inbound_id or rid or conversation_id,
        accepted=False,
        channel="whatsapp_cloud",
        extra_ids=(inbound_mid, inbound_id, f"wa:{mid}" if mid else "", rid, intent_mid, conversation_id),
    )
