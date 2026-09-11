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


def _utc_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _release(tenant_id: str, reservation_id: str | None) -> None:
    if not reservation_id:
        return
    try:
        from services.customer_ai.leftover_reserve import release_leftover_reply

        release_leftover_reply(tenant_id, reservation_id)
    except Exception:
        emit_wa_event("sfu_credit_release_failed", tenant_id=tenant_id)


def _capture(tenant_id: str, reservation_id: str | None) -> bool:
    if not reservation_id:
        return False
    from services.customer_ai.leftover_reserve import capture_leftover_reply

    ok = capture_leftover_reply(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        model_provider="smart_followup",
        operation_id=reservation_id,
    )
    if not ok:
        emit_wa_event("sfu_credit_capture_failed", error="capture_leftover_reply")
    return ok


def _settle_leftover(tenant_id: str, reservation_id: str | None, *, sent: bool) -> None:
    if sent:
        if not _capture(tenant_id, reservation_id):
            from services.membership.reservation_reconcile import hold_failed_capture_after_send

            hold_failed_capture_after_send(
                tenant_id=tenant_id,
                reservation_id=reservation_id,
                operation_id=reservation_id or "",
                billing_policy="legacy_credits",
                channel="smart_followup",
            )
        return
    _release(tenant_id, reservation_id)


def _settle_message_followup(tenant_id: str, snapshot: dict[str, Any], *, accepted: bool) -> None:
    from services.smart_followup.billing_ids import settle_followup_from_snapshot

    settle_followup_from_snapshot(tenant_id, snapshot, accepted=accepted)


def _release_message_followup(tenant_id: str, snapshot: dict[str, Any]) -> None:
    _settle_message_followup(tenant_id, snapshot, accepted=False)


def _finish_attempt_holds(
    tenant_id: str,
    snapshot: dict[str, Any],
    reservation_id: str | None,
    *,
    sent: bool,
) -> None:
    """Confirmed send settles leftover + Brain even if the job fence is already gone."""
    _settle_leftover(tenant_id, reservation_id, sent=sent)
    _settle_message_followup(tenant_id, snapshot, accepted=sent)


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
        from services.membership.feature_entitlements import FeatureDenied, assert_followup_allowed

        try:
            assert_followup_allowed(tenant_id)
        except FeatureDenied:
            sfu.mark_job_terminal(job, status="skipped", reason="plan_followup_disabled")
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": "plan_followup_disabled"}
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
            from services.membership.message_flags import message_billing_enabled
            from services.smart_followup.billing_ids import leftover_followup_pins

            pins = leftover_followup_pins(job)
            if message_billing_enabled():
                reservation_id = str(job.reservation_id or "").strip() or None
                if reservation_id:
                    from services.customer_ai.leftover_reserve import remember_leftover_hold

                    remember_leftover_hold(
                        tenant_id=tenant_id,
                        reservation_id=reservation_id,
                        request_id=canonical_sfu_credit_request_id(job.idempotency_key),
                        operation_type=OPERATION_TYPE,
                        pin_ids=pins,
                    )
            else:
                from services.customer_ai.leftover_reserve import reserve_leftover_reply

                request_id = canonical_sfu_credit_request_id(job.idempotency_key)
                reservation_id = reserve_leftover_reply(
                    tenant_id=tenant_id,
                    request_id=request_id,
                    operation_type=OPERATION_TYPE,
                    pin_ids=pins,
                )
            job.reservation_id = reservation_id
            job.status = "generating"
            session.flush()
        except JobClaimFenceError:
            _release(tenant_id, reservation_id)
            return {"job_id": job_id, "status": "claim_lost"}
        except PermissionError:
            if job is None:
                return {"job_id": job_id, "status": "missing"}
            sfu.mark_job_terminal(job, status="skipped", reason="insufficient_credits")
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": "insufficient_credits"}
        except Exception as exc:
            _release(tenant_id, reservation_id)
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
            operation_id=str(snapshot.get("idempotency_key") or ""),
        )
    except Exception as exc:
        _release_message_followup(tenant_id, snapshot)
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
        _release_message_followup(tenant_id, snapshot)
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
            _release_message_followup(tenant_id, snapshot)
            _release(tenant_id, reservation_id)
            return {"job_id": job_id, "status": "claim_lost"}
        if job is None:
            _release_message_followup(tenant_id, snapshot)
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
            _release_message_followup(tenant_id, snapshot)
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="skipped", reason=reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": reason}

        from services.customer_ai.control import live_handoff_active
        from services.customer_ai.followup.revalidate import revalidate_followup_send

        trigger_at = _utc_dt(getattr(sequence, "trigger_ai_sent_at", None) if sequence else None)
        last_inbound = _utc_dt(getattr(conv, "last_inbound_at", None))
        customer_replied = bool(trigger_at and last_inbound and last_inbound > trigger_at)
        recheck = revalidate_followup_send(
            takeover=live_handoff_active(user_id=conv.user_id or conv.social_sender_id)
            or str(conv.control_state or "") == "HUMAN_PAUSED",
            rule_permits=sequence is not None and str(getattr(sequence, "status", "") or "") == "active",
            window_valid=ok,
            customer_replied=customer_replied or reason == "customer_replied",
            opt_out=reason == "opt_out",
            goal_completed=str(getattr(sequence, "status", "") or "") == "completed",
        )
        if not recheck.allow:
            _release_message_followup(tenant_id, snapshot)
            _release(tenant_id, reservation_id)
            sfu.mark_job_terminal(job, status="skipped", reason=recheck.reason)
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "skipped", "reason": recheck.reason}

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
            _finish_attempt_holds(
                tenant_id,
                snapshot,
                reservation_id,
                sent=send_result.status == "sent",
            )
            return {"job_id": job_id, "status": "claim_lost"}
        if job is None:
            _finish_attempt_holds(
                tenant_id,
                snapshot,
                reservation_id,
                sent=send_result.status == "sent",
            )
            return {"job_id": job_id, "status": "missing"}

        if send_result.status == "sent":
            from services.smart_followup.billing_ids import settle_followup_from_snapshot

            if send_result.reason == "duplicate_delivery" and not send_result.billing_captured:
                sfu.mark_job_terminal(
                    job,
                    status="reconciliation_required",
                    reason="billing_pending",
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=0,
                )
                sfu.maybe_complete_sequence(job.sequence_id)
                return {
                    "job_id": job_id,
                    "status": job.status,
                    "provider_message_id": send_result.provider_message_id,
                    "channel": snapshot["channel"],
                }

            settle_followup_from_snapshot(tenant_id, snapshot, accepted=True)
            leftover_captured = _capture(tenant_id, reservation_id)
            if reservation_id and not leftover_captured:
                from services.membership.hold_policy import hold_billing_policy
                from services.membership.reservation_reconcile import hold_failed_capture_after_send

                hold_failed_capture_after_send(
                    tenant_id=tenant_id,
                    reservation_id=reservation_id,
                    operation_id=str(snapshot.get("idempotency_key") or reservation_id),
                    billing_policy=hold_billing_policy(leftover_reservation_id=reservation_id),
                    provider_message_id=str(send_result.provider_message_id or ""),
                    channel="smart_followup",
                )
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
            elif send_result.billing_pending:
                sfu.mark_job_terminal(
                    job,
                    status="reconciliation_required",
                    reason="billing_pending",
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=0,
                )
            else:
                sfu.mark_job_terminal(
                    job,
                    status="sent",
                    reason=send_result.reason,
                    provider_wamid=send_result.provider_message_id,
                    credits_captured=1 if leftover_captured else 0,
                )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {
                "job_id": job_id,
                "status": job.status,
                "provider_message_id": send_result.provider_message_id,
                "channel": snapshot["channel"],
            }

        if send_result.reconciliation or send_result.status == "reconciliation_required":
            if send_result.provider_message_id:
                from services.membership.hold_policy import hold_billing_policy
                from services.membership.reservation_reconcile import hold_failed_capture_after_send

                hold_failed_capture_after_send(
                    tenant_id=tenant_id,
                    reservation_id=reservation_id,
                    operation_id=str(snapshot.get("idempotency_key") or reservation_id or ""),
                    billing_policy=hold_billing_policy(leftover_reservation_id=reservation_id),
                    provider_message_id=str(send_result.provider_message_id or ""),
                    channel="smart_followup",
                )
            else:
                from services.membership.hold_policy import hold_billing_policy
                from services.membership.pending_settlement import upsert

                upsert(
                    tenant_id=tenant_id,
                    reservation_id=reservation_id or str(snapshot.get("idempotency_key") or ""),
                    operation_id=str(snapshot.get("idempotency_key") or reservation_id or ""),
                    billing_policy=hold_billing_policy(leftover_reservation_id=reservation_id),
                    state="unresolved",
                    reason="unknown_send_outcome",
                    channel="smart_followup",
                )
            sfu.mark_job_terminal(
                job,
                status="reconciliation_required",
                reason=send_result.reason,
                detail=send_result.detail,
            )
            sfu.maybe_complete_sequence(job.sequence_id)
            return {"job_id": job_id, "status": "reconciliation_required", "reason": send_result.reason}

        _release_message_followup(tenant_id, snapshot)
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
