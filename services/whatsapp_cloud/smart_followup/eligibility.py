"""Eligibility gates for Smart Follow-Up sends."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from db.models.whatsapp_cloud import WhatsAppConnection, WhatsAppConversation
from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility, tenant_has_whatsapp_pilot
from services.whatsapp_cloud.smart_followup.business_hours import is_within_business_hours
from services.whatsapp_cloud.smart_followup.constants import CUSTOMER_SERVICE_WINDOW, SAFETY_BUFFER


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def service_window_deadline(conv: WhatsAppConversation) -> datetime | None:
    opened = _aware(conv.service_window_opens_at or conv.last_inbound_at)
    if opened is None:
        return None
    return opened + CUSTOMER_SERVICE_WINDOW


def safe_send_deadline(conv: WhatsAppConversation) -> datetime | None:
    deadline = service_window_deadline(conv)
    if deadline is None:
        return None
    return deadline - SAFETY_BUFFER


def window_allows_send(*, conv: WhatsAppConversation, now: datetime | None = None) -> tuple[bool, str | None]:
    """Free-form follow-ups only while safe customer-service window remains open."""
    now = _aware(now) or datetime.now(UTC)
    opened = _aware(conv.service_window_opens_at or conv.last_inbound_at)
    if opened is None:
        return False, "service_window_unknown"
    if now < opened:
        # Clock skew: treat as not yet open — fail safe.
        return False, "clock_skew_before_window_open"
    hard_deadline = opened + CUSTOMER_SERVICE_WINDOW
    safe_deadline = hard_deadline - SAFETY_BUFFER
    if now >= hard_deadline:
        return False, "customer_service_window_expired"
    if now >= safe_deadline:
        return False, "safety_buffer_insufficient"
    return True, None


def evaluate_job_eligibility(
    session: Session,
    *,
    job: WhatsAppSmartFollowUpJob,
    settings: WhatsAppSmartFollowUpSettings | None,
    conn: WhatsAppConnection | None,
    conv: WhatsAppConversation | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Atomically re-check all send conditions. Returns (ok, reason_code)."""
    now = _aware(now) or datetime.now(UTC)
    flags = get_whatsapp_cloud_flags()

    if settings is None or not settings.enabled:
        return False, "feature_disabled"
    if not flags.ai_replies_enabled:
        return False, "ai_replies_flag_off"
    if not flags.outbound_sends_enabled:
        return False, "outbound_flag_off"
    if conn is None:
        return False, "connection_missing"
    if conn.tenant_id != job.tenant_id:
        return False, "tenant_mismatch"
    if conn.lifecycle_status != "connected":
        return False, "connection_not_connected"
    if conn.lifecycle_status in {"revoked", "failed", "needs_attention", "disconnected"}:
        return False, f"connection_{conn.lifecycle_status}"
    if not conn.ai_default_enabled:
        return False, "ai_default_off"

    # Pilot / public availability — same gate as WhatsApp Cloud AI (no hardcoded tenant bypass).
    if not flags.public_availability:
        if flags.require_pilot_entitlement and not tenant_has_whatsapp_pilot(session, job.tenant_id):
            return False, "pilot_required"

    # Tenant lifecycle (subscription / ban) — fail closed when known suspended.
    suspend_reason = _tenant_suspend_reason(job.tenant_id)
    if suspend_reason:
        return False, suspend_reason

    if conv is None:
        return False, "conversation_missing"
    if conv.control_state != "AI_ACTIVE":
        return False, "conversation_paused"
    if int(conv.control_epoch) != int(job.control_epoch):
        return False, "epoch_changed"

    # Customer replied after trigger (inbound after AI trigger time is cancel — also checked via cancel hooks).
    # Extra safety: if last inbound is after job creation / after due planning relative to AI send.
    ok_window, window_reason = window_allows_send(conv=conv, now=now)
    if not ok_window:
        return False, window_reason or "window_closed"

    if settings.business_hours_only:
        bh_ok, bh_reason = is_within_business_hours(tenant_id=job.tenant_id, now=now)
        if not bh_ok:
            return False, bh_reason or "outside_business_hours"

    ai_ok, ai_reason = evaluate_ai_eligibility(session, conn)
    if not ai_ok:
        return False, ai_reason or "ai_ineligible"

    return True, "eligible"


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
        # Entitlement probe failure must not invent a bypass — treat as unavailable for execution.
        return "tenant_status_unavailable"
    return None


def remaining_safe_seconds(conv: WhatsAppConversation, *, now: datetime | None = None) -> int | None:
    now = _aware(now) or datetime.now(UTC)
    safe = safe_send_deadline(conv)
    if safe is None:
        return None
    delta = safe - now
    return int(delta.total_seconds())
