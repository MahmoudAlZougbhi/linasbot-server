"""AI reply bridge: CM Customer Reply V2 → Cloud send with epoch race checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from db.session import whatsapp_session
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.observability import emit_wa_event, record_analytics_channel_usage
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
    text_body = str(snapshot.get("text_body") or "").strip()
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
    message_type = str(snapshot.get("message_type") or "").lower()
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

    # Reserve credits via canonical ledger before model call.
    reservation_id: str | None = None
    try:
        from services.credit_ledger_service import credit_ledger_service

        reservation_id = credit_ledger_service.reserve(
            tenant_id=tenant_id,
            user_id=None,
            credits=1,
            operation_type="whatsapp_customer_reply",
            request_id=f"wa:{provider_mid}",
        )
    except PermissionError:
        emit_wa_event("insufficient_credits", tenant_id=tenant_id)
        return
    except Exception as exc:
        emit_wa_event("credit_reserve_failed", error=type(exc).__name__)
        return

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
        )
        reply_text = str(
            getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
        ).strip()
        if not reply_text and isinstance(outcome, dict):
            reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
        reason = str(getattr(outcome, "reason", "") or "")
        if reason.endswith("_limit") or reason == "ai_reply_limit":
            _release_reservation(tenant_id, reservation_id)
            reservation_id = None
        if word_notice and reply_text and "limit" not in reason:
            reply_text = f"{word_notice}\n\n{reply_text}"
    except Exception as exc:
        emit_wa_event("ai_generation_failed", error=type(exc).__name__)
        _release_reservation(tenant_id, reservation_id)
        return

    if not reply_text:
        emit_wa_event("ai_empty_reply")
        _release_reservation(tenant_id, reservation_id)
        return

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_connection(connection_id)
        conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
        if conn is None or conv is None or conn.tenant_id != tenant_id:
            _release_reservation(tenant_id, reservation_id)
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
            _release_reservation(tenant_id, reservation_id)
            return

        eligible, eligibility_reason = evaluate_ai_eligibility(session, conn)
        if not eligible:
            emit_wa_event("ai_became_ineligible", reason=eligibility_reason)
            _release_reservation(tenant_id, reservation_id)
            return

        # Customer service window: free-form only within 24h of last inbound.
        now = datetime.now(UTC)
        window_open = conv.service_window_opens_at or conv.last_inbound_at
        if window_open is not None:
            opened = window_open if window_open.tzinfo else window_open.replace(tzinfo=UTC)
            if now - opened > CUSTOMER_SERVICE_WINDOW:
                emit_wa_event("outside_customer_service_window", conversation_id=conversation_id)
                _release_reservation(tenant_id, reservation_id)
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
            _release_reservation(tenant_id, reservation_id)
            return
        if not created and intent.dispatch_state in {"sent", "sending", "suppressed", "reconciliation_required"}:
            _release_reservation(tenant_id, reservation_id)
            return

        repo.update_outbound_intent(
            intent,
            dispatch_state="reply_persisted",
            control_epoch_at_send=int(conv.control_epoch),
            error_detail=reply_text[:500],
        )

        # Capture credits once after valid reply is persisted — delivery retry must not re-charge.
        if reservation_id is not None:
            try:
                from services.credit_ledger_service import credit_ledger_service

                credit_ledger_service.capture(
                    tenant_id=tenant_id,
                    reservation_id=reservation_id,
                    provider_cost_usd=None,
                    model_provider="whatsapp_cloud",
                )
                reservation_id = None  # captured — never release on delivery failure
            except Exception as exc:
                emit_wa_event("credit_capture_failed", error=type(exc).__name__)
                _release_reservation(tenant_id, reservation_id)
                return

        repo.update_outbound_intent(intent, dispatch_state="sending", control_epoch_at_send=int(conv.control_epoch))
        try:
            token = repo.load_access_token(conn)
        except PermissionError:
            repo.update_outbound_intent(intent, dispatch_state="failed", error_code="credential_unavailable")
            _release_reservation(tenant_id, reservation_id)
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
            return
        except Exception as exc:
            # Ambiguous delivery — do not resend; credits already captured for saved reply.
            repo.update_outbound_intent(
                intent,
                dispatch_state="reconciliation_required",
                error_code=type(exc).__name__,
                error_detail="ambiguous_after_submit",
            )
            emit_wa_event("send_ambiguous", error=type(exc).__name__)
            return

        messages = result.get("messages") if isinstance(result, dict) else None
        wamid = ""
        if isinstance(messages, list) and messages:
            wamid = str((messages[0] or {}).get("id") or "")
        repo.update_outbound_intent(intent, dispatch_state="sent", provider_wamid=wamid or None)
        repo.insert_message(
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            provider_message_id=wamid or f"local:{intent.id}",
            origin="CLOUD_API",
            direction="outbound",
            message_type="text",
            content_preview=reply_text[:80],
            status="sent",
            meta={"source": "AI"},
        )
        conv.last_ai_outbound_at = datetime.now(UTC)
        record_analytics_channel_usage(
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            provider_message_id=provider_mid,
            source="ai_reply",
        )
        emit_wa_event("ai_reply_sent", connection_id=connection_id, conversation_id=conversation_id)
        # Smart Follow-Up: absolute-delay sequence after qualifying AI customer-support reply.
        try:
            from services.whatsapp_cloud.smart_followup.hooks import schedule_after_ai_reply

            schedule_after_ai_reply(
                session,
                tenant_id=tenant_id,
                connection_id=connection_id,
                conversation_id=conversation_id,
                trigger_outbound_intent_id=intent.id,
                control_epoch=int(conv.control_epoch),
                trigger_ai_sent_at=conv.last_ai_outbound_at,
                conversation=conv,
            )
        except Exception as exc:
            emit_wa_event("smart_followup_schedule_failed", error=type(exc).__name__)


def _release_reservation(tenant_id: str, reservation_id: str | None) -> None:
    if not reservation_id:
        return
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
    except Exception:
        emit_wa_event("credit_release_failed", tenant_id=tenant_id)


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
