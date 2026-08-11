"""Pilot entitlement + AI eligibility gates for WhatsApp Cloud."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from db.models.whatsapp_cloud import WhatsAppConnection
from services.whatsapp_cloud.config import WHATSAPP_REQUIRED_SCOPES, get_whatsapp_cloud_flags
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


class WhatsAppEntitlementError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def tenant_has_whatsapp_pilot(session: Session, tenant_id: str) -> bool:
    repo = WhatsAppCloudRepository(session)
    return repo.get_active_pilot(tenant_id) is not None


def assert_whatsapp_connection_allowed(session: Session, tenant_id: str) -> None:
    flags = get_whatsapp_cloud_flags()
    if not flags.meta_app_id:
        raise WhatsAppEntitlementError(
            "WHATSAPP_APP_A_NOT_CONFIGURED",
            "Meta App A is not configured for WhatsApp Cloud",
        )
    if not flags.embedded_signup_config_id_configured:
        raise WhatsAppEntitlementError(
            "WHATSAPP_EMBEDDED_SIGNUP_CONFIG_MISSING",
            "META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID is not configured",
        )
    # Phase 2: central public switch opens connect for all eligible tenants (config-only).
    if flags.public_availability:
        return
    if not flags.connection_ui_enabled:
        raise WhatsAppEntitlementError(
            "WHATSAPP_ROLLOUT_DISABLED",
            "WhatsApp Cloud awaits Meta App Review approval before public connect",
        )
    if flags.require_pilot_entitlement and not tenant_has_whatsapp_pilot(session, tenant_id):
        raise WhatsAppEntitlementError(
            "WHATSAPP_PILOT_REQUIRED",
            "WhatsApp Cloud awaits Meta approval. Internal pilot entitlement is required until public rollout",
        )


def evaluate_ai_eligibility(session: Session, conn: WhatsAppConnection) -> tuple[bool, str | None]:
    """AI eligible only after binding + webhook health + CM + entitlement + credits + flags."""

    flags = get_whatsapp_cloud_flags()
    if not flags.ai_replies_enabled:
        return False, "ai_replies_flag_off"
    if conn.lifecycle_status != "connected":
        return False, "connection_not_connected"
    if conn.webhook_subscription_status not in {"ready", "partial"}:
        return False, "webhook_unhealthy"
    if conn.health_status not in {"healthy", "degraded"}:
        return False, "health_unhealthy"
    granted = {str(s) for s in (conn.granted_scopes or [])}
    if not WHATSAPP_REQUIRED_SCOPES.issubset(granted):
        return False, "scopes_missing"
    if flags.require_pilot_entitlement and not tenant_has_whatsapp_pilot(session, conn.tenant_id):
        return False, "pilot_required"
    if conn.history_sync_status in {"pending", "syncing"} and not flags.history_sync_enabled:
        # History still pending is OK for AI if history sync flag is off (skip sync).
        pass
    elif conn.history_sync_status == "syncing":
        return False, "history_sync_in_progress"
    # Published CM required.
    try:
        from services.cm.version_store import load_published_content

        pointer, _sections = load_published_content(conn.tenant_id)
        if not pointer or not getattr(pointer, "content_version_id", None):
            return False, "published_cm_missing"
    except Exception:
        return False, "published_cm_unavailable"
    # Credits: require positive available balance (canonical ledger).
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.ensure_period_grant(conn.tenant_id)
        if credit_ledger_service.get_balance(conn.tenant_id) <= 0:
            return False, "insufficient_credits"
    except Exception:
        return False, "credits_unavailable"
    if not conn.ai_default_enabled:
        return False, "ai_default_off"
    return True, None


def connection_status_payload(session: Session, conn: WhatsAppConnection) -> dict[str, Any]:
    from services.whatsapp_cloud.repository import connection_public_view

    eligible, reason = evaluate_ai_eligibility(session, conn)
    return connection_public_view(conn, ai_eligible=eligible, rollout_blocked_reason=None if eligible else reason)
