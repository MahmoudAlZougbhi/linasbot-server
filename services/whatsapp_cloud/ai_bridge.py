"""AI reply bridge: CM Customer Reply V2 → Cloud send with epoch race checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from db.session import whatsapp_session
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.outbound_finalization import finalize_ai_outbound_sent
from services.whatsapp_cloud.repository import WhatsAppCloudRepository

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


async def maybe_generate_and_send_ai_reply(snapshot: dict[str, Any]) -> None:
    flags = get_whatsapp_cloud_flags()
    if not flags.ai_replies_enabled or not flags.outbound_sends_enabled:
        emit_wa_event("ai_or_outbound_flag_off")
        return

    tenant_id = str(snapshot["tenant_id"])
    connection_id = str(snapshot["connection_id"])
    conversation_id = str(snapshot["conversation_id"])
    inbound_id = str(snapshot.get("message_id") or "")
    provider_mid = str(snapshot.get("provider_message_id") or "")
    raw_text = str(snapshot.get("text_body") or "").strip()
    transcript = str(snapshot.get("transcript") or "").strip()
    message_type = str(snapshot.get("message_type") or "").lower()
    from services.customer_reply_v2.inbound_media import inbound_from_attachment_type

    extract = str(snapshot.get("extract") or snapshot.get("file_extract_preview") or "").strip()
    inbound_media = inbound_from_attachment_type(
        message_type,
        transcript=transcript or (raw_text if message_type == "audio" else ""),
        extract=extract,
    )
    media_id = str(snapshot.get("image_media_id") or snapshot.get("media_id") or "").strip()
    if media_id:
        inbound_media["image_media_id"] = media_id
    if extract:
        inbound_media["extract"] = extract
    text_body = raw_text or transcript
    if not text_body:
        text_body = "Sent a message."
    expected_epoch = int(snapshot.get("control_epoch") or 0)
    customer_wa_id = str(snapshot.get("customer_wa_id") or "")

    from services.ai_limits_enforcement import (
        apply_inbound_word_limit,
        customer_image_limit_message,
        customer_reply_limit_message,
        customer_voice_limit_message,
        enforce_image_analysis_quota,
        enforce_text_reply_quota,
        enforce_voice_minutes_quota,
    )

    limit_user = {
        "tenant_id": tenant_id,
        "social_sender_id": customer_wa_id,
        "phone_number": customer_wa_id,
        "user_preferred_lang": "",
    }
    uid = f"whatsapp:{customer_wa_id}"
    text_body, word_notice = apply_inbound_word_limit(
        user_id=uid,
        user_data=limit_user,
        text=text_body,
    )
    if message_type == "image":
        image_quota = enforce_image_analysis_quota(user_id=uid, user_data=limit_user, amount=1, consume=True)
        if not image_quota.allowed:
            await _send_quota_notice(
                tenant_id=tenant_id,
                connection_id=connection_id,
                conversation_id=conversation_id,
                text=customer_image_limit_message(image_quota),
            )
            emit_wa_event("ai_image_limit", reason=image_quota.reason)
            return
        if image_quota.truncated and image_quota.customer_message:
            word_notice = (
                f"{image_quota.customer_message}\n\n{word_notice}" if word_notice else image_quota.customer_message
            )
    elif message_type == "audio":
        voice_quota = enforce_voice_minutes_quota(
            user_id=uid,
            user_data=limit_user,
            duration_seconds=3600,
            consume=True,
        )
        if not voice_quota.allowed:
            await _send_quota_notice(
                tenant_id=tenant_id,
                connection_id=connection_id,
                conversation_id=conversation_id,
                text=customer_voice_limit_message(voice_quota),
            )
            emit_wa_event("ai_voice_limit", reason=voice_quota.reason)
            return
        if voice_quota.truncated and voice_quota.customer_message:
            word_notice = (
                f"{voice_quota.customer_message}\n\n{word_notice}" if word_notice else voice_quota.customer_message
            )
    reply_precheck = enforce_text_reply_quota(
        user_id=uid,
        user_data=limit_user,
        consume=False,
    )
    if not reply_precheck.allowed:
        await _send_quota_notice(
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            text=customer_reply_limit_message(reply_precheck),
        )
        emit_wa_event("ai_reply_limit", reason=reply_precheck.reason)
        return

    # Credits stay the live gate until message billing replaces them.
    reservation_id: str | None = None
    from services.membership.message_flags import message_billing_enabled

    if not message_billing_enabled():
        try:
            from services.customer_ai.leftover_reserve import reserve_leftover_reply

            reservation_id = reserve_leftover_reply(
                tenant_id=tenant_id,
                request_id=f"wa:{provider_mid}",
                operation_type="whatsapp_customer_reply",
                pin_ids=(provider_mid, inbound_id, conversation_id),
            )
        except PermissionError:
            emit_wa_event("insufficient_credits", tenant_id=tenant_id)
            return
        except Exception as exc:
            emit_wa_event("credit_reserve_failed", error=type(exc).__name__)
            return

    from services.customer_ai.history_ids import message_id_for_brain

    brain_mid = message_id_for_brain(snapshot) or provider_mid

    def release_turn() -> None:
        _release_reservation(
            tenant_id,
            reservation_id,
            inbound_mid=brain_mid,
            inbound_id=inbound_id,
            conversation_id=conversation_id,
        )

    reply_text = ""
    try:
        from services.cm.language_policy import detect_and_resolve_customer_languages
        from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

        _lang = detect_and_resolve_customer_languages(
            tenant_id=tenant_id,
            message=text_body,
            conversation_id=conversation_id,
        )
        outcome = await run_customer_reply_v2_dm(
            tenant_id=tenant_id,
            message=text_body,
            detected_language=_lang["detected_language"],
            response_language=_lang["response_language"],
            channel="whatsapp_dm",
            asset_id=connection_id,
            provider_sender_id=str(snapshot.get("customer_wa_id") or ""),
            provider_display_name=str(snapshot.get("profile_name") or ""),
            user_id=f"whatsapp:{snapshot.get('customer_wa_id')}",
            conversation_id=conversation_id,
            message_id=message_id_for_brain(snapshot),
            inbound_media=inbound_media or None,
        )
        reply_text = str(
            getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
        ).strip()
        if not reply_text and isinstance(outcome, dict):
            reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
        reason = str(getattr(outcome, "reason", "") or "")
        if reason.endswith("_limit") or reason == "ai_reply_limit":
            release_turn()
            reservation_id = None
        if word_notice and reply_text and "limit" not in reason:
            reply_text = f"{word_notice}\n\n{reply_text}"
    except Exception as exc:
        emit_wa_event("ai_generation_failed", error=type(exc).__name__)
        release_turn()
        return

    if not reply_text:
        emit_wa_event("ai_empty_reply")
        release_turn()
        return

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_connection(connection_id)
        conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
        if conn is None or conv is None or conn.tenant_id != tenant_id:
            release_turn()
            return
        # Epoch recheck — manual echo wins the race.
        if conv.control_state != "AI_ACTIVE" or int(conv.control_epoch) != expected_epoch:
            intent, _ = repo.create_outbound_intent(
                tenant_id=tenant_id,
                connection_id=connection_id,
                conversation_id=conversation_id,
                idempotency_key=f"ai:{provider_mid}",
                control_epoch=expected_epoch,
                triggering_inbound_message_id=inbound_id or None,
                source="AI",
            )
            if intent is not None:
                repo.update_outbound_intent(
                    intent,
                    dispatch_state="suppressed",
                    control_epoch_at_send=int(conv.control_epoch),
                    error_code="epoch_race",
                    error_detail="manual_takeover_won_race",
                )
            emit_wa_event("ai_suppression_race", conversation_id=conversation_id)
            release_turn()
            return

        eligible, eligibility_reason = evaluate_ai_eligibility(session, conn)
        if not eligible:
            emit_wa_event("ai_became_ineligible", reason=eligibility_reason)
            release_turn()
            return

        # Customer service window: free-form only within 24h of last inbound.
        now = datetime.now(UTC)
        window_open = conv.service_window_opens_at or conv.last_inbound_at
        if window_open is not None:
            opened = window_open if window_open.tzinfo else window_open.replace(tzinfo=UTC)
            if now - opened > CUSTOMER_SERVICE_WINDOW:
                emit_wa_event("outside_customer_service_window", conversation_id=conversation_id)
                release_turn()
                return

        intent, created = repo.create_outbound_intent(
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            idempotency_key=f"ai:{provider_mid}",
            control_epoch=expected_epoch,
            triggering_inbound_message_id=inbound_id or None,
            source="AI",
        )
        if intent is None:
            release_turn()
            return
        if not created and intent.dispatch_state in {"sent", "suppressed"}:
            release_turn()
            return
        if not created and (intent.dispatch_state == "sending" or str(getattr(intent, "canonical_text", "") or "").strip()):
            _enqueue_whatsapp_intent_deliver(tenant_id=tenant_id, intent_id=intent.id, conversation_id=conversation_id)
            return

        repo.update_outbound_intent(
            intent,
            dispatch_state="pending",
            canonical_text=reply_text,
            control_epoch_at_send=int(conv.control_epoch),
        )

        from services.job_queue import job_queue
        from services.queues.config import redis_required

        if redis_required():
            repo.update_outbound_intent(
                intent,
                dispatch_state="pending",
                canonical_text=reply_text,
                control_epoch_at_send=int(conv.control_epoch),
            )
            session.commit()
            if not getattr(job_queue, "production_ready", False):
                raise RuntimeError("whatsapp_queue_unavailable")
            _enqueue_whatsapp_intent_deliver(tenant_id=tenant_id, intent_id=intent.id, conversation_id=conversation_id)
            emit_wa_event("ai_reply_queued", conversation_id=conversation_id)
            return

        repo.update_outbound_intent(intent, dispatch_state="sending", control_epoch_at_send=int(conv.control_epoch))
        try:
            token = repo.load_access_token(conn)
        except PermissionError:
            repo.update_outbound_intent(intent, dispatch_state="failed", error_code="credential_unavailable")
            release_turn()
            return

        try:
            result = await send_text_message(
                access_token=token,
                phone_number_id=conn.phone_number_id,
                to_wa_id=conv.customer_wa_id,
                text=reply_text,
            )
        except WhatsAppGraphError as exc:
            state = "reconciliation_required" if exc.retryable and exc.http_status in {408, 504, None} else "failed"
            # Ambiguous after submit: network timeout → reconciliation_required, never blind resend.
            if "timeout" in exc.message.lower() or exc.code.endswith("timeout"):
                state = "reconciliation_required"
            repo.update_outbound_intent(
                intent,
                dispatch_state=state,
                error_code=exc.code,
                error_detail=exc.message[:255],
            )
            emit_wa_event("send_failure", code=exc.code, state=state)
            if state == "failed":
                release_turn()
            else:
                _hold_after_ambiguous_send(tenant_id, reservation_id, brain_mid or provider_mid)
            return
        except Exception as exc:
            # Ambiguous delivery — do not resend; keep the hold for reconcile.
            repo.update_outbound_intent(
                intent,
                dispatch_state="reconciliation_required",
                error_code=type(exc).__name__,
                error_detail="ambiguous_after_submit",
            )
            emit_wa_event("send_ambiguous", error=type(exc).__name__)
            _hold_after_ambiguous_send(tenant_id, reservation_id, brain_mid or provider_mid)
            return

        messages = result.get("messages") if isinstance(result, dict) else None
        wamid = ""
        if isinstance(messages, list) and messages:
            wamid = str((messages[0] or {}).get("id") or "")
        finalize_ai_outbound_sent(
            session,
            repo=repo,
            intent=intent,
            conversation=conv,
            canonical_text=reply_text,
            provider_wamid=wamid,
            analytics_provider_message_id=provider_mid,
        )


def _hold_after_ambiguous_send(tenant_id: str, reservation_id: str | None, operation_id: str) -> None:
    """Keep leftover/message holds. Do not mark sent — the provider outcome is unknown."""
    from services.membership.hold_policy import hold_billing_policy
    from services.membership.pending_settlement import upsert

    if not tenant_id or not (reservation_id or operation_id):
        return
    upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id or operation_id,
        operation_id=operation_id or (reservation_id or ""),
        billing_policy=hold_billing_policy(leftover_reservation_id=reservation_id),
        state="unresolved",
        reason="unknown_send_outcome",
        channel="whatsapp_cloud",
    )


def _release_reservation(
    tenant_id: str,
    reservation_id: str | None,
    *,
    inbound_mid: str = "",
    inbound_id: str = "",
    conversation_id: str = "",
) -> None:
    from services.whatsapp_cloud.outbound_finalization import release_unsent_ai_outbound

    release_unsent_ai_outbound(
        tenant_id=tenant_id,
        inbound_mid=inbound_mid,
        inbound_id=inbound_id,
        reservation_id=reservation_id,
        conversation_id=conversation_id,
        intent_mid=inbound_mid,
    )


def _enqueue_whatsapp_intent_deliver(*, tenant_id: str, intent_id: str, conversation_id: str) -> None:
    from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job

    job_id = enqueue_job(
        logical_queue="outbound_whatsapp",
        job_type="whatsapp_intent_deliver",
        tenant_id=tenant_id,
        payload={"intent_id": intent_id},
        idempotency_key=f"wa_del:{intent_id}",
        conversation_key=conversation_id,
        provider="whatsapp",
    )
    if not job_id or job_id == AMBIGUOUS_ENQUEUE:
        raise RuntimeError("whatsapp_intent_deliver_enqueue_failed")


async def _send_quota_notice(
    *,
    tenant_id: str,
    connection_id: str,
    conversation_id: str,
    text: str,
) -> None:
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_connection(connection_id)
        conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
        if conn is None or conv is None:
            return
        try:
            token = repo.load_access_token(conn)
            await send_text_message(
                access_token=token,
                phone_number_id=conn.phone_number_id,
                to_wa_id=conv.customer_wa_id,
                text=text,
            )
        except Exception as exc:
            emit_wa_event("ai_limits_send_failed", error=type(exc).__name__)
