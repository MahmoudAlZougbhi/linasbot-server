"""Durable Smart Follow-Up worker — claim, eligibility, generate, send, exactly-once."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.observability import emit_wa_event, record_analytics_channel_usage
from services.whatsapp_cloud.repository import WhatsAppCloudRepository
from services.whatsapp_cloud.smart_followup.constants import OPERATION_TYPE, WORKER_ID_PREFIX
from services.whatsapp_cloud.smart_followup.eligibility import evaluate_job_eligibility
from services.whatsapp_cloud.smart_followup.generation import generate_followup_text
from services.whatsapp_cloud.smart_followup.repository import SmartFollowUpRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _release(tenant_id: str, reservation_id: str | None) -> None:
    if not reservation_id:
        return
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
    except Exception:
        emit_wa_event("sfu_credit_release_failed", tenant_id=tenant_id)


async def process_due_followup_jobs(*, limit: int = 25) -> dict[str, Any]:
    """Claim and process due jobs. Safe under multi-worker concurrency."""
    worker_id = f"{WORKER_ID_PREFIX}:{uuid.uuid4().hex[:10]}"
    try:
        with whatsapp_session() as session:
            repo = SmartFollowUpRepository(session)
            claimed = repo.claim_due_jobs(worker_id=worker_id, limit=limit)
            job_ids = [j.id for j in claimed]
    except WhatsAppDatabaseUnavailable:
        return {"processed": 0, "reason": "whatsapp_db_unavailable"}

    results: list[dict[str, Any]] = []
    for job_id in job_ids:
        result = await _process_one_job(job_id=job_id, worker_id=worker_id)
        results.append(result)

    return {
        "processed": len(results),
        "worker_id": worker_id,
        "results": results,
    }


async def _process_one_job(*, job_id: str, worker_id: str) -> dict[str, Any]:
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    reservation_id: str | None = None
    tenant_id = ""
    snapshot: dict[str, Any] = {}

    with whatsapp_session() as session:
        sfu = SmartFollowUpRepository(session)
        wa = WhatsAppCloudRepository(session)
        job = session.get(WhatsAppSmartFollowUpJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        if job.status != "claimed" or job.claimed_by != worker_id:
            return {"job_id": job_id, "status": "claim_lost"}

        tenant_id = job.tenant_id
        settings = sfu.get_settings(tenant_id)
        conn = wa.get_connection(job.connection_id)
        conv = wa.get_tenant_conversation(tenant_id=tenant_id, conversation_id=job.conversation_id)
        sequence = sfu.get_sequence(job.sequence_id)

        if sequence is None or sequence.status != "active":
            sfu.mark_job_terminal(job, status="cancelled", reason="sequence_inactive")
            return {"job_id": job_id, "status": "cancelled", "reason": "sequence_inactive"}

        ok, reason = evaluate_job_eligibility(
            session,
            job=job,
            settings=settings,
            conn=conn,
            conv=conv,
        )
        if not ok:
            sfu.mark_job_terminal(job, status="skipped", reason=reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": reason}

        assert conn is not None and conv is not None

        # Reserve credits before generation.
        try:
            from services.credit_ledger_service import credit_ledger_service

            reservation_id = credit_ledger_service.reserve(
                tenant_id=tenant_id,
                user_id=None,
                credits=1,
                operation_type=OPERATION_TYPE,
                request_id=f"sfu:{job.idempotency_key}",
            )
            job.reservation_id = reservation_id
            job.status = "generating"
            session.flush()
        except PermissionError:
            sfu.mark_job_terminal(job, status="skipped", reason="insufficient_credits")
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": "insufficient_credits"}
        except Exception as exc:
            sfu.mark_job_terminal(
                job,
                status="failed",
                reason="credit_reserve_failed",
                detail=type(exc).__name__,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "failed", "reason": "credit_reserve_failed"}

        snapshot = {
            "tenant_id": tenant_id,
            "connection_id": conn.id,
            "conversation_id": conv.id,
            "customer_wa_id": conv.customer_wa_id,
            "profile_name": conv.customer_profile_name,
            "goal": job.goal,
            "control_epoch": int(job.control_epoch),
            "phone_number_id": conn.phone_number_id,
            "reservation_id": reservation_id,
            "job_id": job.id,
            "sequence_id": job.sequence_id,
            "step_index": int(job.step_index),
            "idempotency_key": job.idempotency_key,
        }

    # Generation outside the DB transaction to avoid long locks.
    try:
        reply_text = await generate_followup_text(
            tenant_id=snapshot["tenant_id"],
            connection_id=snapshot["connection_id"],
            conversation_id=snapshot["conversation_id"],
            customer_wa_id=str(snapshot["customer_wa_id"]),
            goal=str(snapshot["goal"]),
            profile_name=str(snapshot.get("profile_name") or ""),
        )
    except Exception as exc:
        _release(tenant_id, reservation_id)
        with whatsapp_session() as session:
            sfu = SmartFollowUpRepository(session)
            job = session.get(WhatsAppSmartFollowUpJob, job_id)
            if job is not None:
                sfu.mark_job_terminal(
                    job,
                    status="failed",
                    reason="generation_failed",
                    detail=type(exc).__name__,
                )
                sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": "failed", "reason": "generation_failed"}

    if not reply_text:
        _release(tenant_id, reservation_id)
        with whatsapp_session() as session:
            sfu = SmartFollowUpRepository(session)
            job = session.get(WhatsAppSmartFollowUpJob, job_id)
            if job is not None:
                sfu.mark_job_terminal(job, status="skipped", reason="empty_generation")
                sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": "skipped", "reason": "empty_generation"}

    # Pre-send atomic recheck + send.
    with whatsapp_session() as session:
        sfu = SmartFollowUpRepository(session)
        wa = WhatsAppCloudRepository(session)
        job = session.get(WhatsAppSmartFollowUpJob, job_id)
        if job is None:
            _release(tenant_id, reservation_id)
            return {"job_id": job_id, "status": "missing"}

        settings = sfu.get_settings(tenant_id)
        conn = wa.get_connection(job.connection_id)
        conv = wa.get_tenant_conversation(tenant_id=tenant_id, conversation_id=job.conversation_id)
        ok, reason = evaluate_job_eligibility(
            session,
            job=job,
            settings=settings,
            conn=conn,
            conv=conv,
        )
        if not ok:
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="skipped", reason=reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": reason}

        assert conn is not None and conv is not None

        # Exactly-once outbound intent for Graph send.
        intent, created = wa.create_outbound_intent(
            tenant_id=tenant_id,
            connection_id=conn.id,
            conversation_id=conv.id,
            idempotency_key=f"sfu:{job.idempotency_key}",
            control_epoch=int(job.control_epoch),
            triggering_inbound_message_id=None,
            source="SMART_FOLLOWUP",
        )
        if intent is None:
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="failed", reason="intent_create_failed")
            return {"job_id": job_id, "status": "failed", "reason": "intent_create_failed"}
        if not created and intent.dispatch_state in {
            "sent",
            "sending",
            "suppressed",
            "reconciliation_required",
        }:
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(
                job,
                status="skipped" if intent.dispatch_state != "sent" else "sent",
                reason="duplicate_outbound_intent",
                provider_wamid=intent.provider_wamid,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "duplicate_suppressed"}

        job.status = "sending"
        wa.update_outbound_intent(intent, dispatch_state="sending", control_epoch_at_send=int(conv.control_epoch))
        try:
            token = wa.load_access_token(conn)
        except PermissionError:
            wa.update_outbound_intent(intent, dispatch_state="failed", error_code="credential_unavailable")
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="failed", reason="credential_unavailable")
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "failed", "reason": "credential_unavailable"}

        phone_number_id = conn.phone_number_id
        to_wa_id = conv.customer_wa_id

    try:
        result = await send_text_message(
            access_token=token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            text=reply_text,
        )
    except WhatsAppGraphError as exc:
        state = (
            "reconciliation_required"
            if (
                (exc.retryable and exc.http_status in {408, 504, None})
                or "timeout" in exc.message.lower()
                or exc.code.endswith("timeout")
            )
            else "failed"
        )
        with whatsapp_session() as session:
            sfu = SmartFollowUpRepository(session)
            wa = WhatsAppCloudRepository(session)
            job = session.get(WhatsAppSmartFollowUpJob, job_id)
            intent_row, _ = wa.create_outbound_intent(
                tenant_id=tenant_id,
                connection_id=snapshot["connection_id"],
                conversation_id=snapshot["conversation_id"],
                idempotency_key=f"sfu:{snapshot['idempotency_key']}",
                control_epoch=int(snapshot["control_epoch"]),
                triggering_inbound_message_id=None,
                source="SMART_FOLLOWUP",
            )
            if intent_row is not None:
                wa.update_outbound_intent(
                    intent_row,
                    dispatch_state=state,
                    error_code=exc.code,
                    error_detail=exc.message[:255],
                )
            if job is not None:
                # Ambiguous Graph state: never blind-resend; do not release if reconciliation.
                if state == "reconciliation_required":
                    sfu.mark_job_terminal(
                        job,
                        status="reconciliation_required",
                        reason=exc.code,
                        detail=exc.message[:255],
                    )
                else:
                    _release(tenant_id, reservation_id)
                    sfu.mark_job_terminal(
                        job,
                        status="failed",
                        reason=exc.code,
                        detail=exc.message[:255],
                    )
                sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": state, "reason": exc.code}
    except Exception as exc:
        # Ambiguous after submit — reconciliation, do not resend, keep reservation held? Spec: release on clear fail;
        # ambiguous → reconciliation and do not blindly resend. Release credits since message may not have been generated charge?
        # Credits were for AI generation which succeeded — capture would be wrong if not sent.
        # Spec: capture actual AI usage once. Generation happened — capture even if send failed? Spec for credits:
        # "Capture actual AI usage once" — generation consumed AI, so capture; send is separate Meta cost.
        # But if send failed clearly, we still used AI. Capture on generation success.
        with whatsapp_session() as session:
            sfu = SmartFollowUpRepository(session)
            wa = WhatsAppCloudRepository(session)
            job = session.get(WhatsAppSmartFollowUpJob, job_id)
            intent_row, _ = wa.create_outbound_intent(
                tenant_id=tenant_id,
                connection_id=snapshot["connection_id"],
                conversation_id=snapshot["conversation_id"],
                idempotency_key=f"sfu:{snapshot['idempotency_key']}",
                control_epoch=int(snapshot["control_epoch"]),
                triggering_inbound_message_id=None,
                source="SMART_FOLLOWUP",
            )
            if intent_row is not None:
                wa.update_outbound_intent(
                    intent_row,
                    dispatch_state="reconciliation_required",
                    error_code=type(exc).__name__,
                    error_detail="ambiguous_after_submit",
                )
            if job is not None:
                # Capture AI usage (generation completed) then mark reconciliation.
                try:
                    from services.credit_ledger_service import credit_ledger_service

                    if reservation_id:
                        credit_ledger_service.capture(
                            tenant_id=tenant_id,
                            reservation_id=reservation_id,
                            provider_cost_usd=None,
                            model_provider="whatsapp_cloud",
                        )
                        reservation_id = None
                except Exception:
                    pass
                sfu.mark_job_terminal(
                    job,
                    status="reconciliation_required",
                    reason="ambiguous_after_submit",
                    detail=type(exc).__name__,
                    credits_captured=1,
                )
                sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": "reconciliation_required"}

    messages = result.get("messages") if isinstance(result, dict) else None
    wamid = ""
    if isinstance(messages, list) and messages:
        wamid = str((messages[0] or {}).get("id") or "")

    with whatsapp_session() as session:
        sfu = SmartFollowUpRepository(session)
        wa = WhatsAppCloudRepository(session)
        job = session.get(WhatsAppSmartFollowUpJob, job_id)
        conn = wa.get_connection(snapshot["connection_id"])
        conv = wa.get_tenant_conversation(
            tenant_id=tenant_id,
            conversation_id=snapshot["conversation_id"],
        )
        intent_row, _ = wa.create_outbound_intent(
            tenant_id=tenant_id,
            connection_id=snapshot["connection_id"],
            conversation_id=snapshot["conversation_id"],
            idempotency_key=f"sfu:{snapshot['idempotency_key']}",
            control_epoch=int(snapshot["control_epoch"]),
            triggering_inbound_message_id=None,
            source="SMART_FOLLOWUP",
        )
        if intent_row is not None:
            wa.update_outbound_intent(intent_row, dispatch_state="sent", provider_wamid=wamid or None)
        if conv is not None:
            wa.insert_message(
                tenant_id=tenant_id,
                connection_id=snapshot["connection_id"],
                conversation_id=conv.id,
                provider_message_id=wamid or f"local:sfu:{job_id}",
                origin="CLOUD_API",
                direction="outbound",
                message_type="text",
                content_preview=reply_text[:80],
                status="sent",
                meta={"source": "SMART_FOLLOWUP", "goal": snapshot["goal"], "step_index": snapshot["step_index"]},
            )
            conv.last_ai_outbound_at = _utcnow()
        try:
            from services.credit_ledger_service import credit_ledger_service

            if reservation_id:
                credit_ledger_service.capture(
                    tenant_id=tenant_id,
                    reservation_id=reservation_id,
                    provider_cost_usd=None,
                    model_provider="whatsapp_cloud",
                )
        except Exception as exc:
            emit_wa_event("sfu_credit_capture_failed", error=type(exc).__name__)
        if job is not None:
            sfu.mark_job_terminal(
                job,
                status="sent",
                reason="sent",
                provider_wamid=wamid or None,
                credits_captured=1,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
        record_analytics_channel_usage(
            tenant_id=tenant_id,
            connection_id=snapshot["connection_id"],
            conversation_id=snapshot["conversation_id"],
            provider_message_id=wamid or job_id,
            source="smart_followup",
        )
        emit_wa_event(
            "smart_followup_sent",
            tenant_id=tenant_id,
            conversation_id=snapshot["conversation_id"],
            step_index=snapshot["step_index"],
        )

    return {"job_id": job_id, "status": "sent", "provider_wamid": wamid}
