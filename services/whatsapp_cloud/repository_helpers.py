"""WhatsApp Cloud repository helpers and public views (LOC split)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from db.models.whatsapp_cloud import WhatsAppConnection, WhatsAppConversation

ACTIVE_LIFECYCLES = frozenset(
    {
        "connected",
        "provisioning",
        "syncing_history",
        "needs_attention",
        "awaiting_meta",
        "starting",
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mask_id(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


def _mask_phone_wa_id(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def connection_public_view(
    conn: WhatsAppConnection,
    *,
    ai_eligible: bool,
    rollout_blocked_reason: str | None = None,
) -> dict[str, Any]:
    from services.whatsapp_cloud.types import ConnectionPublicView

    view = ConnectionPublicView(
        connection_id=conn.id,
        tenant_id=conn.tenant_id,
        lifecycle_status=conn.lifecycle_status,  # type: ignore[arg-type]
        coexistence_mode=conn.coexistence_mode,
        connection_source=conn.connection_source,
        display_phone_last4=conn.display_phone_last4,
        verified_name=conn.verified_name,
        waba_id_masked=_mask_id(conn.waba_id),
        phone_number_id_masked=_mask_id(conn.phone_number_id),
        webhook_subscription_status=conn.webhook_subscription_status,
        health_status=conn.health_status,
        health_detail=conn.health_detail,
        ai_eligible=ai_eligible,
        ai_default_enabled=bool(conn.ai_default_enabled),
        history_sync_status=conn.history_sync_status,
        granted_scopes=list(conn.granted_scopes or []),
        rollout_blocked_reason=rollout_blocked_reason,
    )
    return view.to_dict()


def conversation_public_view(conv: WhatsAppConversation) -> dict[str, Any]:
    from services.whatsapp_cloud.types import ConversationPublicView

    view = ConversationPublicView(
        conversation_id=conv.id,
        connection_id=conv.connection_id,
        control_state=conv.control_state,  # type: ignore[arg-type]
        control_epoch=int(conv.control_epoch),
        pause_reason=conv.pause_reason,
        customer_wa_id_masked=_mask_phone_wa_id(conv.customer_wa_id),
        customer_profile_name=str(conv.customer_profile_name or "")[:64],
    )
    return view.to_dict()
