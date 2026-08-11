"""Lifecycle hooks: schedule after AI reply; cancel on reply/pause/disable."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.smart_followup.eligibility import safe_send_deadline
from services.whatsapp_cloud.smart_followup.repository import SmartFollowUpRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


def schedule_after_ai_reply(
    session: Session,
    *,
    tenant_id: str,
    connection_id: str,
    conversation_id: str,
    trigger_outbound_intent_id: str,
    control_epoch: int,
    trigger_ai_sent_at: datetime | None = None,
    conversation: Any | None = None,
) -> dict[str, Any]:
    """Start a new absolute-delay sequence after a qualifying outbound AI reply."""
    repo = SmartFollowUpRepository(session)
    settings, steps = repo.ensure_defaults(tenant_id)
    if not settings.enabled:
        return {"scheduled": False, "reason": "feature_disabled"}

    enabled_steps = [s for s in steps if s.enabled]
    if not enabled_steps:
        return {"scheduled": False, "reason": "no_enabled_steps"}

    sent_at = trigger_ai_sent_at or _utcnow()
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)

    # Newer AI reply replaces any prior active sequence for this conversation.
    repo.supersede_active_for_conversation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason="newer_ai_reply",
    )

    seq, created = repo.create_sequence(
        tenant_id=tenant_id,
        connection_id=connection_id,
        conversation_id=conversation_id,
        trigger_outbound_intent_id=trigger_outbound_intent_id,
        trigger_ai_sent_at=sent_at,
        control_epoch=control_epoch,
        settings_version=int(settings.settings_version),
    )
    if seq is None:
        return {"scheduled": False, "reason": "sequence_create_failed"}
    if not created:
        return {"scheduled": False, "reason": "duplicate_trigger", "sequence_id": seq.id}

    safe_deadline = None
    if conversation is not None:
        safe_deadline = safe_send_deadline(conversation)

    jobs_created = 0
    for step in enabled_steps:
        due_at = sent_at + timedelta(minutes=int(step.delay_minutes))
        # Never schedule past the safe customer-service window.
        if safe_deadline is not None and due_at >= safe_deadline:
            repo.record_event(
                tenant_id=tenant_id,
                event_type="job_not_scheduled",
                reason_code="due_past_safe_window",
                connection_id=connection_id,
                conversation_id=conversation_id,
                sequence_id=seq.id,
                detail={"step_index": step.step_index, "delay_minutes": step.delay_minutes},
            )
            continue
        job, job_created = repo.create_job(
            sequence=seq,
            step_index=int(step.step_index),
            goal=str(step.goal),
            delay_minutes=int(step.delay_minutes),
            due_at=due_at,
        )
        if job_created and job is not None:
            jobs_created += 1
            repo.record_event(
                tenant_id=tenant_id,
                event_type="job_scheduled",
                connection_id=connection_id,
                conversation_id=conversation_id,
                sequence_id=seq.id,
                job_id=job.id,
                detail={"step_index": step.step_index, "due_at": due_at.isoformat()},
            )

    if jobs_created == 0:
        seq.status = "completed"
        seq.cancel_reason = "no_schedulable_steps"
        seq.cancelled_at = _utcnow()
        return {"scheduled": False, "reason": "no_schedulable_steps", "sequence_id": seq.id}

    emit_wa_event(
        "smart_followup_scheduled",
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        jobs=jobs_created,
    )
    return {
        "scheduled": True,
        "sequence_id": seq.id,
        "jobs_created": jobs_created,
    }


def cancel_conversation_followups(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    reason: str,
) -> int:
    repo = SmartFollowUpRepository(session)
    count = repo.cancel_active_for_conversation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason=reason,
    )
    if count:
        emit_wa_event(
            "smart_followup_cancelled",
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=reason,
            jobs=count,
        )
    return count


def cancel_tenant_followups(session: Session, *, tenant_id: str, reason: str) -> int:
    repo = SmartFollowUpRepository(session)
    return repo.cancel_active_for_tenant(tenant_id=tenant_id, reason=reason)


def cancel_connection_followups(
    session: Session,
    *,
    tenant_id: str,
    connection_id: str,
    reason: str,
) -> int:
    repo = SmartFollowUpRepository(session)
    count = repo.cancel_active_for_connection(
        tenant_id=tenant_id,
        connection_id=connection_id,
        reason=reason,
    )
    if count:
        emit_wa_event(
            "smart_followup_cancelled",
            tenant_id=tenant_id,
            connection_id=connection_id,
            reason=reason,
            jobs=count,
        )
    return count
