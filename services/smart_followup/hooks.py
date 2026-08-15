"""Lifecycle hooks: schedule after AI reply; cancel on reply/pause/disable."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT, SOURCE_CHANNEL_WHATSAPP_CLOUD
from services.smart_followup.channels import normalize_followup_channel
from services.smart_followup.constants import DEFAULT_CHANNEL
from services.smart_followup.repository import SmartFollowUpRepository
from services.smart_followup.settings_service import channel_enabled_for_settings
from services.smart_followup.types import FollowUpConversationView, FollowUpScheduleRequest
from services.smart_followup.window_rules import safe_send_deadline
from services.whatsapp_cloud.observability import emit_wa_event


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _conversation_view_from_request(
    request: FollowUpScheduleRequest,
    *,
    conversation: Any | None = None,
) -> FollowUpConversationView | None:
    if conversation is not None and request.channel == SOURCE_CHANNEL_WHATSAPP_CLOUD:
        return FollowUpConversationView(
            channel=request.channel,
            tenant_id=request.tenant_id,
            conversation_id=request.conversation_id,
            connection_id=request.connection_id,
            control_epoch=request.control_epoch,
            control_state=str(getattr(conversation, "control_state", "AI_ACTIVE")),
            service_window_opens_at=getattr(conversation, "service_window_opens_at", None),
            last_inbound_at=getattr(conversation, "last_inbound_at", None),
            profile_name=str(getattr(conversation, "customer_profile_name", "") or ""),
            customer_wa_id=str(getattr(conversation, "customer_wa_id", "") or ""),
        )
    ctx = dict(request.channel_context or {})
    last_inbound = ctx.get("last_inbound_at")
    opened = None
    if isinstance(last_inbound, datetime):
        opened = last_inbound
    elif isinstance(last_inbound, str) and last_inbound.strip():
        try:
            opened = datetime.fromisoformat(last_inbound.replace("Z", "+00:00"))
        except ValueError:
            opened = None
    return FollowUpConversationView(
        channel=request.channel,
        tenant_id=request.tenant_id,
        conversation_id=request.conversation_id,
        connection_id=request.connection_id,
        control_epoch=request.control_epoch,
        control_state="AI_ACTIVE",
        service_window_opens_at=opened,
        last_inbound_at=opened,
        profile_name=str(ctx.get("profile_name") or ""),
        user_id=str(ctx.get("user_id") or ""),
        social_sender_id=str(ctx.get("social_sender_id") or ""),
        asset_id=str(ctx.get("asset_id") or ""),
        meta_binding_id=str(ctx.get("meta_binding_id") or request.connection_id),
        meta_app_key=str(ctx.get("meta_app_key") or ""),
        trigger_ref=str(ctx.get("trigger_ref") or request.trigger_ref),
    )


def schedule_followup_sequence(
    session: Session,
    *,
    request: FollowUpScheduleRequest,
    conversation: Any | None = None,
) -> dict[str, Any]:
    repo = SmartFollowUpRepository(session)
    settings, steps = repo.ensure_defaults(request.tenant_id)
    if not settings.enabled:
        return {"scheduled": False, "reason": "feature_disabled"}

    enabled_steps = [s for s in steps if s.enabled]
    if not enabled_steps:
        return {"scheduled": False, "reason": "no_enabled_steps"}

    channel = normalize_followup_channel(request.channel or DEFAULT_CHANNEL)
    if channel == SOURCE_CHANNEL_WEB_CHAT:
        from services.web_chat.flags import web_chat_containment_active

        if web_chat_containment_active():
            return {"scheduled": False, "reason": "web_chat_contained"}
    if not channel_enabled_for_settings(settings, channel):
        return {"scheduled": False, "reason": "channel_disabled"}

    sent_at = request.trigger_ai_sent_at or _utcnow()
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)

    repo.supersede_active_for_conversation(
        tenant_id=request.tenant_id,
        conversation_id=request.conversation_id,
        reason="newer_ai_reply",
    )

    seq, created = repo.create_sequence(
        tenant_id=request.tenant_id,
        channel=channel,
        connection_id=request.connection_id,
        conversation_id=request.conversation_id,
        trigger_outbound_intent_id=request.trigger_ref,
        trigger_ai_sent_at=sent_at,
        control_epoch=request.control_epoch,
        settings_version=int(settings.settings_version),
        channel_context=request.channel_context,
    )
    if seq is None:
        return {"scheduled": False, "reason": "sequence_create_failed"}
    if not created:
        return {"scheduled": False, "reason": "duplicate_trigger", "sequence_id": seq.id}

    conv_view = _conversation_view_from_request(request, conversation=conversation)
    safe_deadline = safe_send_deadline(conv_view) if conv_view is not None else None

    jobs_created = 0
    for step in enabled_steps:
        due_at = sent_at + timedelta(minutes=int(step.delay_minutes))
        if safe_deadline is not None and due_at >= safe_deadline:
            repo.record_event(
                tenant_id=request.tenant_id,
                event_type="job_not_scheduled",
                reason_code="due_past_safe_window",
                connection_id=request.connection_id,
                conversation_id=request.conversation_id,
                sequence_id=seq.id,
                detail={"step_index": step.step_index, "delay_minutes": step.delay_minutes, "channel": channel},
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
                tenant_id=request.tenant_id,
                event_type="job_scheduled",
                connection_id=request.connection_id,
                conversation_id=request.conversation_id,
                sequence_id=seq.id,
                job_id=job.id,
                detail={"step_index": step.step_index, "due_at": due_at.isoformat(), "channel": channel},
            )

    if jobs_created == 0:
        seq.status = "completed"
        seq.cancel_reason = "no_schedulable_steps"
        seq.cancelled_at = _utcnow()
        return {"scheduled": False, "reason": "no_schedulable_steps", "sequence_id": seq.id}

    emit_wa_event(
        "smart_followup_scheduled",
        tenant_id=request.tenant_id,
        conversation_id=request.conversation_id,
        jobs=jobs_created,
        channel=channel,
    )
    return {"scheduled": True, "sequence_id": seq.id, "jobs_created": jobs_created, "channel": channel}


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
    channel: str = SOURCE_CHANNEL_WHATSAPP_CLOUD,
    channel_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return schedule_followup_sequence(
        session,
        request=FollowUpScheduleRequest(
            tenant_id=tenant_id,
            channel=channel,
            connection_id=connection_id,
            conversation_id=conversation_id,
            trigger_ref=trigger_outbound_intent_id,
            control_epoch=control_epoch,
            trigger_ai_sent_at=trigger_ai_sent_at,
            channel_context=channel_context or {},
        ),
        conversation=conversation,
    )


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
