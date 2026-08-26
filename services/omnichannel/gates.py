"""Capability gates. Code may exist; live traffic stays fail-closed until approved."""

from __future__ import annotations

from typing import Any

TIKTOK_DM_GATE_REASON = "tiktok_messaging_permission_pending"
WHATSAPP_PUBLIC_GATE_REASON = "whatsapp_advanced_access_pending"


def tiktok_dm_live_allowed(connection: Any | None = None) -> tuple[bool, str]:
    from services.cm.actions import ACTION_TIKTOK_DM, action_enabled, load_actions_section
    from services.tiktok_business.scopes import messaging_send_ready

    if connection is None:
        return False, TIKTOK_DM_GATE_REASON
    tenant_id = str(getattr(connection, "tenant_id", "") or "")
    actions = load_actions_section(tenant_id)
    if not action_enabled(actions, ACTION_TIKTOK_DM):
        return False, TIKTOK_DM_GATE_REASON
    if not messaging_send_ready(getattr(connection, "granted_scopes", None) or []):
        return False, TIKTOK_DM_GATE_REASON
    return True, ""


def whatsapp_public_onboarding_live() -> tuple[bool, str]:
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    flags = get_whatsapp_cloud_flags()
    if not bool(getattr(flags, "public_availability", False)):
        return False, WHATSAPP_PUBLIC_GATE_REASON
    return True, ""
