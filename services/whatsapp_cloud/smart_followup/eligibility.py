"""Backward-compatible eligibility helpers for WhatsApp Cloud callers."""

from __future__ import annotations

from datetime import UTC, datetime

from db.models.whatsapp_cloud import WhatsAppConnection, WhatsAppConversation
from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.smart_followup.types import FollowUpConversationView
from services.smart_followup.window_rules import (
    remaining_safe_seconds as _remaining_safe_seconds,
    safe_send_deadline as _safe_send_deadline,
    service_window_deadline as _service_window_deadline,
    window_allows_send as _window_allows_send,
)
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.entitlement import evaluate_ai_eligibility, tenant_has_whatsapp_pilot
from sqlalchemy.orm import Session


def _to_view(conv: WhatsAppConversation) -> FollowUpConversationView:
    return FollowUpConversationView(
        channel="whatsapp_cloud",
        tenant_id=str(conv.tenant_id),
        conversation_id=str(conv.id),
        connection_id=str(conv.connection_id),
        control_epoch=int(conv.control_epoch),
        control_state=str(conv.control_state),
        service_window_opens_at=conv.service_window_opens_at,
        last_inbound_at=conv.last_inbound_at,
        profile_name=str(conv.customer_profile_name or ""),
        customer_wa_id=str(conv.customer_wa_id or ""),
    )


def service_window_deadline(conv: WhatsAppConversation) -> datetime | None:
    return _service_window_deadline(_to_view(conv))


def safe_send_deadline(conv: WhatsAppConversation) -> datetime | None:
    return _safe_send_deadline(_to_view(conv))


def window_allows_send(*, conv: WhatsAppConversation, now: datetime | None = None) -> tuple[bool, str | None]:
    return _window_allows_send(conv=_to_view(conv), now=now)


def remaining_safe_seconds(conv: WhatsAppConversation, *, now: datetime | None = None) -> int | None:
    return _remaining_safe_seconds(_to_view(conv), now=now)


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
    conn: WhatsAppConnection | None,
    conv: WhatsAppConversation | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    if settings is None or not settings.enabled:
        return False, "feature_disabled"

    suspend_reason = _tenant_suspend_reason(job.tenant_id)
    if suspend_reason:
        return False, suspend_reason

    if conv is None:
        return False, "conversation_missing"

    view = _to_view(conv)
    if conv.control_state != "AI_ACTIVE":
        return False, "conversation_paused"
    if int(conv.control_epoch) != int(job.control_epoch):
        return False, "epoch_changed"

    ok_window, window_reason = _window_allows_send(conv=view, now=now)
    if not ok_window:
        return False, window_reason or "window_closed"

    if settings.business_hours_only:
        from services.smart_followup.business_hours import is_within_business_hours

        bh_ok, bh_reason = is_within_business_hours(tenant_id=job.tenant_id, now=now or datetime.now(UTC))
        if not bh_ok:
            return False, bh_reason or "outside_business_hours"

    flags = get_whatsapp_cloud_flags()
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
    if not flags.public_availability:
        if flags.require_pilot_entitlement and not tenant_has_whatsapp_pilot(session, job.tenant_id):
            return False, "pilot_required"
    ai_ok, ai_reason = evaluate_ai_eligibility(session, conn)
    if not ai_ok:
        return False, ai_reason or "ai_ineligible"
    return True, "eligible"
