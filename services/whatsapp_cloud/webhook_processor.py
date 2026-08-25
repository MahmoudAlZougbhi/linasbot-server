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
    claim_id: str | None = None

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
        unfinished = (
            (not is_new)
            and claim.processing_state == "claimed"
            and event.event_kind == "inbound_message"
            and conn is not None
        )
        if not is_new and not unfinished:
            emit_wa_event("duplicate_suppressed", event_kind=event.event_kind)
            return "duplicate"
        if conn is None:
            repo.complete_webhook_event(claim, state="ignored")
            emit_wa_event("unknown_asset", phone_prefix=(event.phone_number_id or "")[:4])
            return "ignored"

        if unfinished:
            conv = repo.get_or_create_conversation(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                customer_wa_id=event.customer_wa_id,
                profile_name=event.profile_name,
            )
            ai_eligible, ai_reason = evaluate_ai_eligibility(session, conn)
            ai_snapshot = _ai_snapshot(conn=conn, conv=conv, event=event, message_id=None)
            claim_id = claim.id
            emit_wa_event("claimed_unfinished_retry", conversation_id=conv.id)
        elif event.event_kind in {
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
            try:
                from services.whatsapp_cloud.smart_followup.hooks import cancel_conversation_followups

                cancel_conversation_followups(
                    session,
                    tenant_id=conn.tenant_id,
                    conversation_id=conv.id,
                    reason="business_app_echo",
                )
            except Exception as exc:
                emit_wa_event("smart_followup_cancel_failed", error=type(exc).__name__)
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
            # Customer reply / opt-out cancels remaining Smart Follow-Up jobs.
            try:
                from services.whatsapp_cloud.smart_followup.hooks import cancel_conversation_followups
                from services.whatsapp_cloud.smart_followup.opt_out import looks_like_opt_out

                cancel_reason = "opt_out" if looks_like_opt_out(event.text_body) else "customer_reply"
                cancel_conversation_followups(
                    session,
                    tenant_id=conn.tenant_id,
                    conversation_id=conv.id,
                    reason=cancel_reason,
                )
            except Exception as exc:
                emit_wa_event("smart_followup_cancel_failed", error=type(exc).__name__)
            ai_eligible, ai_reason = evaluate_ai_eligibility(session, conn)
            ai_snapshot = _ai_snapshot(conn=conn, conv=conv, event=event, message_id=msg.id if msg else None)
            claim_id = claim.id
        else:
            repo.complete_webhook_event(claim, state="ignored")
            return "ignored"

    if ai_snapshot is None:
        return "accepted"
    if ai_snapshot["control_state"] != "AI_ACTIVE":
        emit_wa_event("ai_suppressed_paused", conversation_id=ai_snapshot["conversation_id"])
        _finish_claim_without_ai(claim_id)
        return "accepted"
    if not ai_eligible:
        emit_wa_event(
            "ai_suppressed_ineligible",
            reason=ai_reason,
            conversation_id=ai_snapshot["conversation_id"],
        )
        _finish_claim_without_ai(claim_id)
        return "accepted"
    if event.message_type in {"unsupported", "reaction", "sticker"} and not event.text_body:
        emit_wa_event("unsupported_no_ai", message_type=event.message_type)
        _finish_claim_without_ai(claim_id)
        return "accepted"
    from services.job_queue import job_queue
    from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job, should_defer_to_worker

    if should_defer_to_worker():
        if not getattr(job_queue, "production_ready", False):
            raise RuntimeError("whatsapp_queue_unavailable")
        job_id = enqueue_job(
            logical_queue="dm_urgent",
            job_type="whatsapp_generate",
            tenant_id=str(ai_snapshot["tenant_id"]),
            payload=ai_snapshot,
            idempotency_key=f"wa_ai:{ai_snapshot['provider_message_id']}",
            conversation_key=str(ai_snapshot["conversation_id"]),
            provider="whatsapp",
        )
        if job_id is None or job_id == AMBIGUOUS_ENQUEUE:
            raise RuntimeError("whatsapp_generate_enqueue_failed")
    else:
        await maybe_generate_and_send_ai_reply(ai_snapshot)
    _complete_claimed_webhook(claim_id)
    record_analytics_channel_usage(
        tenant_id=ai_snapshot["tenant_id"],
        connection_id=ai_snapshot["connection_id"],
        conversation_id=ai_snapshot["conversation_id"],
        provider_message_id=ai_snapshot["provider_message_id"],
        source="customer_inbound",
    )
    return "accepted"


def _ai_snapshot(*, conn: Any, conv: Any, event: ParsedCloudEvent, message_id: str | None) -> dict[str, Any]:
    return {
        "tenant_id": conn.tenant_id,
        "connection_id": conn.id,
        "conversation_id": conv.id,
        "customer_wa_id": conv.customer_wa_id,
        "control_state": conv.control_state,
        "control_epoch": int(conv.control_epoch),
        "message_id": message_id,
        "provider_message_id": event.provider_message_id,
        "message_type": event.message_type,
        "text_body": event.text_body,
        "media_id": event.media_id,
        "profile_name": event.profile_name,
    }


def _finish_claim_without_ai(claim_id: str | None) -> None:
    _complete_claimed_webhook(claim_id)


def _complete_claimed_webhook(claim_id: str | None) -> None:
    if not claim_id:
        return
    from db.models.whatsapp_cloud import WhatsAppWebhookEvent

    with whatsapp_session() as session:
        row = session.get(WhatsAppWebhookEvent, claim_id)
        if row is not None and row.processing_state == "claimed":
            WhatsAppCloudRepository(session).complete_webhook_event(row, state="processed")
            session.commit()
