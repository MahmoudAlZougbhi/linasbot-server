"""Process one Smart Follow-Up job via channel adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.smart_followup.channels import get_channel_adapter, normalize_followup_channel
from services.smart_followup.constants import OPERATION_TYPE
from services.smart_followup.eligibility import evaluate_job_eligibility_async
from services.smart_followup.generation import generate_followup_text
from services.smart_followup.idempotency import canonical_sfu_credit_request_id, canonical_sfu_key
from services.smart_followup.job_fence import JobClaimFenceError, assert_job_claim_fence, claim_generation_of
from services.smart_followup.repository import SmartFollowUpRepository
from services.whatsapp_cloud.observability import emit_wa_event


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


def _sender_id_for_generation(job: Any, conv: Any) -> tuple[str, str]:
    channel = normalize_followup_channel(getattr(job, "channel", None) or conv.channel)
    if channel == "whatsapp_cloud":
        return str(conv.customer_wa_id or ""), f"whatsapp:{conv.customer_wa_id}"
    return str(conv.social_sender_id or conv.user_id or ""), str(conv.user_id or conv.social_sender_id or "")


def _fence_job(session: Any, *, job_id: str, worker_id: str, claim_generation: int) -> Any | None:
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    job = session.get(WhatsAppSmartFollowUpJob, job_id)
    if job is None:
        return None
    assert_job_claim_fence(job, worker_id=worker_id, claim_generation=claim_generation)
    return job


async def process_one_followup_job(*, job_id: str, worker_id: str) -> dict[str, Any]:
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    reservation_id: str | None = None
    tenant_id = ""
    snapshot: dict[str, Any] = {}
    claim_generation = 0

    with whatsapp_session() as session:
        sfu = SmartFollowUpRepository(session)
        job = session.get(WhatsAppSmartFollowUpJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        if job.status != "claimed" or job.claimed_by != worker_id:
            return {"job_id": job_id, "status": "claim_lost"}
        claim_generation = claim_generation_of(job)

        tenant_id = job.tenant_id
        settings = sfu.get_settings(tenant_id)
        sequence = sfu.get_sequence(job.sequence_id)
        if sequence is None or sequence.status != "active":
            sfu.mark_job_terminal(job, status="cancelled", reason="sequence_inactive")
            return {"job_id": job_id, "status": "cancelled", "reason": "sequence_inactive"}

        adapter = get_channel_adapter(job.channel)
        conv = adapter.load_conversation(session, job=job)
        ok, reason, conv = await evaluate_job_eligibility_async(
            session,
            job=job,
            settings=settings,
            conv=conv,
            trigger_ai_sent_at=sequence.trigger_ai_sent_at,
        )
        if not ok or conv is None:
            sfu.mark_job_terminal(job, status="skipped", reason=reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": reason}

        try:
            job = _fence_job(session, job_id=job_id, worker_id=worker_id, claim_generation=claim_generation)
            if job is None:
                return {"job_id": job_id, "status": "missing"}
            from services.credit_ledger_service import credit_ledger_service

            reservation_id = credit_ledger_service.reserve(
                tenant_id=tenant_id,
                user_id=None,
                credits=1,
                operation_type=OPERATION_TYPE,
                request_id=canonical_sfu_credit_request_id(job.idempotency_key),
            )
            job.reservation_id = reservation_id
            job.status = "generating"
            session.flush()
        except JobClaimFenceError:
            return {"job_id": job_id, "status": "claim_lost"}
        except PermissionError:
            if job is None:
                return {"job_id": job_id, "status": "missing"}
            sfu.mark_job_terminal(job, status="skipped", reason="insufficient_credits")
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": "insufficient_credits"}
        except Exception as exc:
            if job is None:
                return {"job_id": job_id, "status": "missing"}
            sfu.mark_job_terminal(
                job,
                status="failed",
                reason="credit_reserve_failed",
                detail=type(exc).__name__,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "failed", "reason": "credit_reserve_failed"}

        sender_id, user_id = _sender_id_for_generation(job, conv)
        snapshot = {
            "tenant_id": tenant_id,
            "channel": normalize_followup_channel(job.channel),
            "connection_id": job.connection_id,
            "conversation_id": conv.conversation_id,
            "goal": job.goal,
            "control_epoch": int(job.control_epoch),
            "reservation_id": reservation_id,
            "job_id": job.id,
            "sequence_id": job.sequence_id,
            "step_index": int(job.step_index),
            "idempotency_key": job.idempotency_key,
            "sender_id": sender_id,
            "user_id": user_id,
            "profile_name": conv.profile_name,
        }

    try:
        reply_text = await generate_followup_text(
            tenant_id=snapshot["tenant_id"],
            channel=snapshot["channel"],
            connection_id=snapshot["connection_id"],
            conversation_id=snapshot["conversation_id"],
            customer_sender_id=str(snapshot["sender_id"]),
            goal=str(snapshot["goal"]),
            profile_name=str(snapshot.get("profile_name") or ""),
            user_id=str(snapshot.get("user_id") or ""),
        )
    except Exception as exc:
        _release(tenant_id, reservation_id)
        with whatsapp_session() as session:
            try:
                job = _fence_job(session, job_id=job_id, worker_id=worker_id, claim_generation=claim_generation)
            except JobClaimFenceError:
                return {"job_id": job_id, "status": "claim_lost"}
            if job is not None:
                sfu = SmartFollowUpRepository(session)
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
            try:
                job = _fence_job(session, job_id=job_id, worker_id=worker_id, claim_generation=claim_generation)
            except JobClaimFenceError:
                return {"job_id": job_id, "status": "claim_lost"}
            if job is not None:
                sfu = SmartFollowUpRepository(session)
                sfu.mark_job_terminal(job, status="skipped", reason="empty_generation")
                sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": "skipped", "reason": "empty_generation"}

    with whatsapp_session() as session:
        try:
            job = _fence_job(session, job_id=job_id, worker_id=worker_id, claim_generation=claim_generation)
        except JobClaimFenceError:
            _release(tenant_id, reservation_id)
            return {"job_id": job_id, "status": "claim_lost"}
        if job is None:
            _release(tenant_id, reservation_id)
            return {"job_id": job_id, "status": "missing"}

        sfu = SmartFollowUpRepository(session)
        settings = sfu.get_settings(tenant_id)
        sequence = sfu.get_sequence(job.sequence_id)
        adapter = get_channel_adapter(job.channel)
        conv = adapter.load_conversation(session, job=job)
        ok, reason, conv = await evaluate_job_eligibility_async(
            session,
            job=job,
            settings=settings,
            conv=conv,
            trigger_ai_sent_at=sequence.trigger_ai_sent_at if sequence else None,
        )
        if not ok or conv is None:
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="skipped", reason=reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": reason}

        job.status = "sending"
        session.flush()
        send_result = await adapter.send_followup(
            session,
            job=job,
            conv=conv,
            reply_text=reply_text,
            idempotency_key=canonical_sfu_key(job.idempotency_key),
        )

        try:
            job = _fence_job(session, job_id=job_id, worker_id=worker_id, claim_generation=claim_generation)
        except JobClaimFenceError:
            return {"job_id": job_id, "status": "claim_lost"}
        if job is None:
            return {"job_id": job_id, "status": "missing"}

        if send_result.status == "sent":
            if send_result.reason == "duplicate_delivery":
                if send_result.billing_captured:
                    sfu.mark_job_terminal(
                        job,
                        status="sent",
                        reason=send_result.reason,
                        provider_wamid=send_result.provider_message_id,
                        credits_captured=1,
                    )
                else:
                    sfu.mark_job_terminal(
                        job,
                        status="reconciliation_required",
                        reason="billing_pending",
                        provider_wamid=send_result.provider_message_id,
                        credits_captured=0,
                    )
            elif send_result.billing_captured:
                sfu.mark_job_terminal(
                    job,
                    status="sent",
                    reason=send_result.reason,
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=1,
                )
            elif send_result.billing_pending or snapshot.get("channel") == "web_chat":
                sfu.mark_job_terminal(
                    job,
                    status="reconciliation_required",
                    reason="billing_pending",
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=0,
                )
            else:
                credits_captured = 0
                try:
                    from services.credit_ledger_service import credit_ledger_service

                    if reservation_id:
                        credit_ledger_service.capture(
                            tenant_id=tenant_id,
                            reservation_id=reservation_id,
                            provider_cost_usd=None,
                            model_provider="smart_followup",
                        )
                        credits_captured = 1
                except Exception as exc:
                    emit_wa_event("sfu_credit_capture_failed", error=type(exc).__name__)
                    sfu.mark_job_terminal(
                        job,
                        status="reconciliation_required",
                        reason="billing_pending",
                        detail=type(exc).__name__,
                        provider_wamid=send_result.provider_message_id,
                        credits_captured=0,
                    )
                    sfu.maybe_complete_sequence(job.sequence_id)
                    return {"job_id": job_id, "status": "reconciliation_required", "reason": "billing_pending"}
                sfu.mark_job_terminal(
                    job,
                    status="sent",
                    reason=send_result.reason,
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=credits_captured,
                )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {
                "job_id": job_id,
                "status": job.status,
                "provider_message_id": send_result.provider_message_id,
                "channel": snapshot["channel"],
            }

        if send_result.reconciliation or send_result.status == "reconciliation_required":
            sfu.mark_job_terminal(
                job,
                status="reconciliation_required",
                reason=send_result.reason,
                detail=send_result.detail,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "reconciliation_required", "reason": send_result.reason}

        _release(tenant_id, reservation_id)
        terminal = "skipped" if send_result.status == "skipped" else "failed"
        sfu.mark_job_terminal(
            job,
            status=terminal,
            reason=send_result.reason,
            detail=send_result.detail,
        )
        sfu.maybe_complete_sequence(job.sequence_id)
        return {"job_id": job_id, "status": terminal, "reason": send_result.reason}
