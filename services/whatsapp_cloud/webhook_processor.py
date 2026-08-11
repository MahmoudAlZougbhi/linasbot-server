"""Inbound WhatsApp Cloud webhook processing with coexistence invariants."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.whatsapp_cloud.ai_bridge import maybe_generate_and_send_ai_reply
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility
from services.whatsapp_cloud.observability import emit_wa_event, record_analytics_channel_usage
from services.whatsapp_cloud.repository import WhatsAppCloudRepository
from services.whatsapp_cloud.types import ParsedCloudEvent
from services.whatsapp_cloud.webhook_parser import parse_whatsapp_cloud_payload, payload_hash


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def process_whatsapp_cloud_webhook(
    *,
    raw_body: bytes,
    payload: dict[str, Any],
) -> dict[str, Any]:
    flags = get_whatsapp_cloud_flags()
    if not flags.webhook_side_effects_enabled:
        emit_wa_event("webhook_side_effects_disabled")
        return {"status": "ignored", "reason": "webhook_side_effects_disabled", "accepted": 0}

    events = parse_whatsapp_cloud_payload(payload)
    if not events:
        return {"status": "ignored", "reason": "no_whatsapp_events", "accepted": 0}

    body_fp = payload_hash(raw_body)
    accepted = 0
    duplicates = 0

    for event in events:
        result = await _process_one_event(event, body_fp=body_fp)
        if result == "accepted":
            accepted += 1
        elif result == "duplicate":
            duplicates += 1

    return {
        "status": "ok",
        "accepted": accepted,
        "duplicates": duplicates,
    }


async def _process_one_event(event: ParsedCloudEvent, *, body_fp: str) -> str:
    ai_snapshot: dict[str, Any] | None = None
    ai_eligible = False
    ai_reason: str | None = None

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        conn = repo.find_active_by_phone_number_id(event.phone_number_id) if event.phone_number_id else None
        claim, is_new = repo.claim_webhook_event(
            event_key=event.event_key,
            event_kind=event.event_kind,
            payload_hash=hashlib.sha256(f"{event.event_key}:{body_fp}".encode()).hexdigest(),
            tenant_id=conn.tenant_id if conn else None,
            connection_id=conn.id if conn else None,
        )
        if claim is None:
            return "error"
        if not is_new:
            emit_wa_event("duplicate_suppressed", event_kind=event.event_kind)
            return "duplicate"
        if conn is None:
            repo.complete_webhook_event(claim, state="ignored")
            emit_wa_event("unknown_asset", phone_prefix=(event.phone_number_id or "")[:4])
            return "ignored"

        if event.event_kind in {
            "history",
            "smb_app_state_sync",
            "status",
            "template",
            "account_update",
            "phone_quality",
        }:
            if event.event_kind == "history" and get_whatsapp_cloud_flags().history_sync_enabled:
                conn.history_sync_status = "syncing"
            if event.event_kind == "history" and conn.history_sync_status == "syncing":
                conn.history_sync_status = "complete"
            if event.event_kind in {"account_update", "phone_quality"}:
                conn.health_status = "needs_attention"
                conn.health_detail = event.event_kind
                conn.lifecycle_status = "needs_attention"
            conn.webhook_last_success_at = _utcnow()
            repo.complete_webhook_event(claim, state="processed")
            emit_wa_event("non_ai_event", event_kind=event.event_kind, connection_id=conn.id)
            return "accepted"

        if event.event_kind == "smb_message_echoes":
            conv = repo.get_or_create_conversation(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                customer_wa_id=event.customer_wa_id or "unknown",
                profile_name=event.profile_name,
            )
            repo.insert_message(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                conversation_id=conv.id,
                provider_message_id=event.provider_message_id,
                origin="BUSINESS_APP",
                direction="outbound",
                message_type=event.message_type,
                content_preview=None,
                meta={"echo": True},
                status="echoed",
            )
            repo.pause_conversation(conv, reason="business_app_echo", actor_user_id=None)
            conn.webhook_last_success_at = _utcnow()
            repo.complete_webhook_event(claim, state="processed")
            emit_wa_event("manual_takeover", connection_id=conn.id, conversation_id=conv.id)
            return "accepted"

        if event.event_kind == "inbound_message":
            conv = repo.get_or_create_conversation(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                customer_wa_id=event.customer_wa_id,
                profile_name=event.profile_name,
            )
            preview = (event.text_body or "")[:80] if event.text_body else f"[{event.message_type}]"
            msg, created = repo.insert_message(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                conversation_id=conv.id,
                provider_message_id=event.provider_message_id,
                origin="CUSTOMER",
                direction="inbound",
                message_type=event.message_type,
                content_preview=preview,
                media_id=event.media_id or None,
                media_mime=event.media_mime or None,
            )
            if not created:
                repo.complete_webhook_event(claim, state="processed")
                return "duplicate"
            conv.last_inbound_at = _utcnow()
            conv.service_window_opens_at = _utcnow()
            conn.webhook_last_success_at = _utcnow()
            ai_eligible, ai_reason = evaluate_ai_eligibility(session, conn)
            ai_snapshot = {
                "tenant_id": conn.tenant_id,
                "connection_id": conn.id,
                "conversation_id": conv.id,
                "customer_wa_id": conv.customer_wa_id,
                "control_state": conv.control_state,
                "control_epoch": int(conv.control_epoch),
                "message_id": msg.id if msg else None,
                "provider_message_id": event.provider_message_id,
                "message_type": event.message_type,
                "text_body": event.text_body,
                "media_id": event.media_id,
                "profile_name": event.profile_name,
            }
            repo.complete_webhook_event(claim, state="processed")
        else:
            repo.complete_webhook_event(claim, state="ignored")
            return "ignored"

    if ai_snapshot is None:
        return "accepted"
    if ai_snapshot["control_state"] != "AI_ACTIVE":
        emit_wa_event("ai_suppressed_paused", conversation_id=ai_snapshot["conversation_id"])
        return "accepted"
    if not ai_eligible:
        emit_wa_event(
            "ai_suppressed_ineligible",
            reason=ai_reason,
            conversation_id=ai_snapshot["conversation_id"],
        )
        return "accepted"
    if event.message_type in {"unsupported", "reaction", "sticker"} and not event.text_body:
        emit_wa_event("unsupported_no_ai", message_type=event.message_type)
        return "accepted"
    await maybe_generate_and_send_ai_reply(ai_snapshot)
    record_analytics_channel_usage(
        tenant_id=ai_snapshot["tenant_id"],
        connection_id=ai_snapshot["connection_id"],
        conversation_id=ai_snapshot["conversation_id"],
        provider_message_id=ai_snapshot["provider_message_id"],
        source="customer_inbound",
    )
    return "accepted"
