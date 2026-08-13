"""Shared + channel-routed eligibility gates for Smart Follow-Up."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.smart_followup.business_hours import is_within_business_hours
from services.smart_followup.channels import get_channel_adapter, normalize_followup_channel
from services.smart_followup.types import FollowUpConversationView


def _tenant_suspend_reason(tenant_id: str) -> str | None:
    try:
        from services.entitlements_service import get_tenant_entitlement_public

        public = get_tenant_entitlement_public(tenant_id)
        status = str(public.get("status") or public.get("lifecycle_status") or "").lower()
        if status in {"suspended", "blocked", "banned", "revoked"}:
            return f"tenant_{status}"
        if public.get("banned") is True or public.get("blocked") is True:
            return "tenant_blocked"
    except Exception:
        return "tenant_status_unavailable"
    return None


def evaluate_job_eligibility(
    session: Session,
    *,
    job: WhatsAppSmartFollowUpJob,
    settings: WhatsAppSmartFollowUpSettings | None,
    conv: FollowUpConversationView | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = now if now is not None else datetime.now(UTC)
    if settings is None or not settings.enabled:
        return False, "feature_disabled"

    suspend_reason = _tenant_suspend_reason(job.tenant_id)
    if suspend_reason:
        return False, suspend_reason

    if conv is None:
        return False, "conversation_missing"

    if settings.business_hours_only:
        bh_ok, bh_reason = is_within_business_hours(tenant_id=job.tenant_id, now=now)
        if not bh_ok:
            return False, bh_reason or "outside_business_hours"

    adapter = get_channel_adapter(normalize_followup_channel(job.channel))
    return adapter.evaluate_channel_eligibility(
        session,
        job=job,
        settings=settings,
        conv=conv,
        now=now,
    )


async def evaluate_job_eligibility_async(
    session: Session,
    *,
    job: WhatsAppSmartFollowUpJob,
    settings: WhatsAppSmartFollowUpSettings | None,
    conv: FollowUpConversationView | None,
    trigger_ai_sent_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[bool, str, FollowUpConversationView | None]:
    """Meta channels refresh Firestore takeover/window state before eligibility."""
    channel = normalize_followup_channel(getattr(job, "channel", None) or conv.channel if conv else "")
    if conv is not None and channel in {"instagram_dm", "facebook_messenger"}:
        from services.smart_followup.adapters.meta_dm import MetaDmFollowUpAdapter

        adapter = MetaDmFollowUpAdapter(channel=channel)
        refreshed, reason = await adapter.refresh_conversation(conv=conv, trigger_ai_sent_at=trigger_ai_sent_at)
        if refreshed is None:
            return False, reason or "conversation_unavailable", None
        conv = refreshed

    ok, reason = evaluate_job_eligibility(session, job=job, settings=settings, conv=conv, now=now)
    return ok, reason, conv
