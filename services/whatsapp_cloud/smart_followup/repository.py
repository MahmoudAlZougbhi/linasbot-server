"""Repository helpers for Smart Follow-Up PG SoT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import (
    WhatsAppSmartFollowUpEvent,
    WhatsAppSmartFollowUpJob,
    WhatsAppSmartFollowUpSequence,
    WhatsAppSmartFollowUpSettings,
    WhatsAppSmartFollowUpStep,
)
from services.whatsapp_cloud.smart_followup.constants import (
    CLAIM_BATCH_SIZE,
    CLAIM_STALE_SECONDS,
    DEFAULT_STEPS,
    TERMINAL_JOB_STATUSES,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class SmartFollowUpRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_settings(self, tenant_id: str) -> WhatsAppSmartFollowUpSettings | None:
        return self.session.scalar(
            select(WhatsAppSmartFollowUpSettings).where(WhatsAppSmartFollowUpSettings.tenant_id == tenant_id)
        )

    def list_steps(self, settings_id: str) -> list[WhatsAppSmartFollowUpStep]:
        rows = self.session.scalars(
            select(WhatsAppSmartFollowUpStep)
            .where(WhatsAppSmartFollowUpStep.settings_id == settings_id)
            .order_by(WhatsAppSmartFollowUpStep.step_index.asc())
        ).all()
        return list(rows)

    def ensure_defaults(self, tenant_id: str) -> tuple[WhatsAppSmartFollowUpSettings, list[WhatsAppSmartFollowUpStep]]:
        settings = self.get_settings(tenant_id)
        if settings is None:
            settings = WhatsAppSmartFollowUpSettings(
                id=_uuid(),
                tenant_id=tenant_id,
                enabled=False,
                business_hours_only=True,
                billing_mode="customer_direct",
                settings_version=1,
            )
            self.session.add(settings)
            self.session.flush()
            for raw in DEFAULT_STEPS:
                self.session.add(
                    WhatsAppSmartFollowUpStep(
                        id=_uuid(),
                        settings_id=settings.id,
                        tenant_id=tenant_id,
                        step_index=raw["step_index"],
                        enabled=raw["enabled"],
                        delay_minutes=raw["delay_minutes"],
                        goal=raw["goal"],
                    )
                )
            self.session.flush()
        steps = self.list_steps(settings.id)
        return settings, steps

    def replace_steps(
        self,
        *,
        settings: WhatsAppSmartFollowUpSettings,
        steps_payload: list[dict[str, Any]],
    ) -> list[WhatsAppSmartFollowUpStep]:
        existing = self.list_steps(settings.id)
        for row in existing:
            self.session.delete(row)
        self.session.flush()
        created: list[WhatsAppSmartFollowUpStep] = []
        for raw in steps_payload:
            step = WhatsAppSmartFollowUpStep(
                id=_uuid(),
                settings_id=settings.id,
                tenant_id=settings.tenant_id,
                step_index=int(raw["step_index"]),
                enabled=bool(raw.get("enabled", True)),
                delay_minutes=int(raw["delay_minutes"]),
                goal=str(raw["goal"]),
            )
            self.session.add(step)
            created.append(step)
        self.session.flush()
        return created

    def record_event(
        self,
        *,
        tenant_id: str,
        event_type: str,
        reason_code: str | None = None,
        connection_id: str | None = None,
        conversation_id: str | None = None,
        sequence_id: str | None = None,
        job_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> WhatsAppSmartFollowUpEvent:
        ev = WhatsAppSmartFollowUpEvent(
            id=_uuid(),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            sequence_id=sequence_id,
            job_id=job_id,
            event_type=event_type,
            reason_code=reason_code,
            detail=detail or {},
        )
        self.session.add(ev)
        return ev

    def create_sequence(
        self,
        *,
        tenant_id: str,
        connection_id: str,
        conversation_id: str,
        trigger_outbound_intent_id: str,
        trigger_ai_sent_at: datetime,
        control_epoch: int,
        settings_version: int,
    ) -> tuple[WhatsAppSmartFollowUpSequence | None, bool]:
        existing = self.session.scalar(
            select(WhatsAppSmartFollowUpSequence).where(
                WhatsAppSmartFollowUpSequence.tenant_id == tenant_id,
                WhatsAppSmartFollowUpSequence.conversation_id == conversation_id,
                WhatsAppSmartFollowUpSequence.trigger_outbound_intent_id == trigger_outbound_intent_id,
            )
        )
        if existing is not None:
            return existing, False
        seq = WhatsAppSmartFollowUpSequence(
            id=_uuid(),
            tenant_id=tenant_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            trigger_outbound_intent_id=trigger_outbound_intent_id,
            trigger_ai_sent_at=trigger_ai_sent_at,
            control_epoch=control_epoch,
            settings_version=settings_version,
            status="active",
        )
        self.session.add(seq)
        self.session.flush()
        return seq, True

    def create_job(
        self,
        *,
        sequence: WhatsAppSmartFollowUpSequence,
        step_index: int,
        goal: str,
        delay_minutes: int,
        due_at: datetime,
    ) -> tuple[WhatsAppSmartFollowUpJob | None, bool]:
        idempotency_key = f"sfu:{sequence.id}:{step_index}"
        existing = self.session.scalar(
            select(WhatsAppSmartFollowUpJob).where(WhatsAppSmartFollowUpJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        job = WhatsAppSmartFollowUpJob(
            id=_uuid(),
            tenant_id=sequence.tenant_id,
            connection_id=sequence.connection_id,
            conversation_id=sequence.conversation_id,
            sequence_id=sequence.id,
            step_index=step_index,
            goal=goal,
            delay_minutes=delay_minutes,
            due_at=due_at,
            status="scheduled",
            control_epoch=sequence.control_epoch,
            idempotency_key=idempotency_key,
        )
        self.session.add(job)
        self.session.flush()
        return job, True

    def cancel_active_for_conversation(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        reason: str,
    ) -> int:
        now = _utcnow()
        sequences = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpSequence).where(
                    WhatsAppSmartFollowUpSequence.tenant_id == tenant_id,
                    WhatsAppSmartFollowUpSequence.conversation_id == conversation_id,
                    WhatsAppSmartFollowUpSequence.status == "active",
                )
            ).all()
        )
        cancelled = 0
        for seq in sequences:
            seq.status = "cancelled"
            seq.cancel_reason = reason
            seq.cancelled_at = now
            jobs = list(
                self.session.scalars(
                    select(WhatsAppSmartFollowUpJob).where(
                        WhatsAppSmartFollowUpJob.sequence_id == seq.id,
                        WhatsAppSmartFollowUpJob.status.in_(["scheduled", "claimed", "generating", "sending"]),
                    )
                ).all()
            )
            for job in jobs:
                job.status = "cancelled"
                job.result_reason = reason
                job.completed_at = now
                cancelled += 1
                self.record_event(
                    tenant_id=tenant_id,
                    event_type="job_cancelled",
                    reason_code=reason,
                    connection_id=seq.connection_id,
                    conversation_id=conversation_id,
                    sequence_id=seq.id,
                    job_id=job.id,
                )
            self.record_event(
                tenant_id=tenant_id,
                event_type="sequence_cancelled",
                reason_code=reason,
                connection_id=seq.connection_id,
                conversation_id=conversation_id,
                sequence_id=seq.id,
            )
        return cancelled

    def cancel_active_for_tenant(self, *, tenant_id: str, reason: str) -> int:
        sequences = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpSequence).where(
                    WhatsAppSmartFollowUpSequence.tenant_id == tenant_id,
                    WhatsAppSmartFollowUpSequence.status == "active",
                )
            ).all()
        )
        total = 0
        for seq in sequences:
            total += self.cancel_active_for_conversation(
                tenant_id=tenant_id,
                conversation_id=seq.conversation_id,
                reason=reason,
            )
        return total

    def supersede_active_for_conversation(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        reason: str = "newer_ai_reply",
    ) -> int:
        now = _utcnow()
        sequences = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpSequence).where(
                    WhatsAppSmartFollowUpSequence.tenant_id == tenant_id,
                    WhatsAppSmartFollowUpSequence.conversation_id == conversation_id,
                    WhatsAppSmartFollowUpSequence.status == "active",
                )
            ).all()
        )
        count = 0
        for seq in sequences:
            seq.status = "superseded"
            seq.cancel_reason = reason
            seq.cancelled_at = now
            jobs = list(
                self.session.scalars(
                    select(WhatsAppSmartFollowUpJob).where(
                        WhatsAppSmartFollowUpJob.sequence_id == seq.id,
                        WhatsAppSmartFollowUpJob.status.in_(["scheduled", "claimed", "generating", "sending"]),
                    )
                ).all()
            )
            for job in jobs:
                job.status = "cancelled"
                job.result_reason = reason
                job.completed_at = now
                count += 1
        return count

    def claim_due_jobs(self, *, worker_id: str, limit: int = CLAIM_BATCH_SIZE) -> list[WhatsAppSmartFollowUpJob]:
        now = _utcnow()
        stale_before = now - timedelta(seconds=CLAIM_STALE_SECONDS)
        # Reclaim stale claims (worker crash). Compare in Python for SQLite tz-naive rows.
        stale_candidates = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpJob).where(
                    WhatsAppSmartFollowUpJob.status.in_(["claimed", "generating", "sending"]),
                    WhatsAppSmartFollowUpJob.claimed_at.is_not(None),
                )
            ).all()
        )
        for row in stale_candidates:
            claimed_at = row.claimed_at
            if claimed_at is None:
                continue
            if claimed_at.tzinfo is None:
                claimed_at = claimed_at.replace(tzinfo=UTC)
            if claimed_at < stale_before:
                row.status = "scheduled"
                row.claimed_at = None
                row.claimed_by = None
        self.session.flush()

        due_candidates = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpJob)
                .where(WhatsAppSmartFollowUpJob.status == "scheduled")
                .order_by(WhatsAppSmartFollowUpJob.due_at.asc())
                .limit(limit * 3)
            ).all()
        )
        due: list[WhatsAppSmartFollowUpJob] = []
        for job in due_candidates:
            due_at = job.due_at
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=UTC)
            if due_at <= now:
                due.append(job)
            if len(due) >= limit:
                break
        claimed: list[WhatsAppSmartFollowUpJob] = []
        for job in due:
            result = self.session.execute(
                update(WhatsAppSmartFollowUpJob)
                .where(
                    and_(
                        WhatsAppSmartFollowUpJob.id == job.id,
                        WhatsAppSmartFollowUpJob.status == "scheduled",
                    )
                )
                .values(
                    status="claimed",
                    claimed_at=now,
                    claimed_by=worker_id,
                    attempt_count=int(job.attempt_count or 0) + 1,
                )
            )
            if int(getattr(result, "rowcount", 0) or 0) == 1:
                self.session.refresh(job)
                claimed.append(job)
        return claimed

    def get_sequence(self, sequence_id: str) -> WhatsAppSmartFollowUpSequence | None:
        return self.session.get(WhatsAppSmartFollowUpSequence, sequence_id)

    def mark_job_terminal(
        self,
        job: WhatsAppSmartFollowUpJob,
        *,
        status: str,
        reason: str,
        detail: str | None = None,
        provider_wamid: str | None = None,
        credits_captured: int = 0,
    ) -> None:
        job.status = status
        job.result_reason = reason
        if detail is not None:
            job.result_detail = detail[:255]
        if provider_wamid is not None:
            job.provider_wamid = provider_wamid
        if credits_captured:
            job.credits_captured = credits_captured
        if status in TERMINAL_JOB_STATUSES:
            job.completed_at = _utcnow()
        self.record_event(
            tenant_id=job.tenant_id,
            event_type=f"job_{status}",
            reason_code=reason,
            connection_id=job.connection_id,
            conversation_id=job.conversation_id,
            sequence_id=job.sequence_id,
            job_id=job.id,
            detail={"step_index": job.step_index},
        )

    def maybe_complete_sequence(self, sequence_id: str) -> None:
        seq = self.get_sequence(sequence_id)
        if seq is None or seq.status != "active":
            return
        jobs = list(
            self.session.scalars(
                select(WhatsAppSmartFollowUpJob).where(WhatsAppSmartFollowUpJob.sequence_id == sequence_id)
            ).all()
        )
        if not jobs:
            return
        if all(j.status in TERMINAL_JOB_STATUSES for j in jobs):
            seq.status = "completed"
            self.record_event(
                tenant_id=seq.tenant_id,
                event_type="sequence_completed",
                connection_id=seq.connection_id,
                conversation_id=seq.conversation_id,
                sequence_id=seq.id,
            )
