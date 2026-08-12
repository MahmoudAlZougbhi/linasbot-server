"""Server-authoritative manual chat mode: pause AI on first operator send; Resume AI clears it.

SoT:
- Meta IG/FB / Firestore Live Chat: `human_takeover_active` + in-memory flag
- WhatsApp Cloud: Postgres `control_state` / `control_epoch` (AI send rechecks epoch)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from services.requests.constants import (
    EVENT_MANUAL_PAUSE,
    EVENT_MANUAL_RESUME,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)
from services.requests.repository import CustomerRequestsRepository

PAUSE_REASON_MANUAL_SEND = "manual_operator_send"


@dataclass(frozen=True)
class ManualModeResult:
    conversation_id: str
    activated: bool
    already_active: bool
    control_epoch: int | None
    channel: str | None
    audit_recorded: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _pause_whatsapp_cloud(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    actor_user_id: str,
) -> tuple[bool, int | None]:
    """Pause WA Cloud AI. Returns (changed, control_epoch)."""
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    repo = WhatsAppCloudRepository(session)
    conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
    if conv is None:
        return False, None
    if conv.control_state == "HUMAN_PAUSED":
        return False, int(conv.control_epoch)
    repo.pause_conversation(
        conv,
        reason=PAUSE_REASON_MANUAL_SEND,
        actor_user_id=actor_user_id,
    )
    return True, int(conv.control_epoch)


def _resume_whatsapp_cloud(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    actor_user_id: str,
) -> tuple[bool, int | None]:
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    repo = WhatsAppCloudRepository(session)
    conv = repo.get_tenant_conversation(tenant_id=tenant_id, conversation_id=conversation_id)
    if conv is None:
        return False, None
    if conv.control_state == "AI_ACTIVE":
        return False, int(conv.control_epoch)
    repo.resume_conversation(conv, actor_user_id=actor_user_id)
    return True, int(conv.control_epoch)


async def _pause_firestore(
    *,
    conversation_id: str,
    user_id: str,
    actor_user_id: str,
    operator_name: str | None,
) -> bool:
    """Set Firestore + in-memory takeover. Returns True when write attempted."""
    import config
    from utils.utils import get_canonical_user_id_and_phone, set_human_takeover_status

    canonical, _ = get_canonical_user_id_and_phone(user_id)
    # In-memory first so same-process in-flight AI sees pause before Firestore round-trip.
    for vid in {canonical, user_id}:
        if vid:
            config.user_in_human_takeover_mode[vid] = True
    await set_human_takeover_status(
        user_id,
        conversation_id,
        True,
        operator_id=actor_user_id,
        operator_name=operator_name,
        request_user_id=user_id,
    )
    return True


async def _resume_firestore(*, conversation_id: str, user_id: str) -> bool:
    import config
    from utils.utils import get_canonical_user_id_and_phone, set_human_takeover_status

    canonical, _ = get_canonical_user_id_and_phone(user_id)
    for vid in {canonical, user_id}:
        if vid:
            config.user_in_human_takeover_mode[vid] = False
    await set_human_takeover_status(
        user_id,
        conversation_id,
        False,
        request_user_id=user_id,
    )
    return True


def _record_audit_once(
    session: Session,
    *,
    tenant_id: str,
    request_id: str,
    actor_user_id: str,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> bool:
    repo = CustomerRequestsRepository(session)
    existing = repo.get_idempotency(tenant_id=tenant_id, scope=event_type, key=idempotency_key)
    if existing is not None:
        return False
    repo.add_event(
        tenant_id=tenant_id,
        request_id=request_id,
        event_type=event_type,
        actor_kind="operator",
        actor_user_id=actor_user_id,
        payload=payload,
    )
    repo.put_idempotency(
        tenant_id=tenant_id,
        scope=event_type,
        key=idempotency_key,
        request_id=request_id,
    )
    return True


async def activate_manual_mode(
    *,
    conversation_id: str,
    user_id: str,
    actor_user_id: str,
    tenant_id: str | None = None,
    operator_name: str | None = None,
    request_id: str | None = None,
    source_channel: str | None = None,
    session: Session | None = None,
) -> ManualModeResult:
    """Pause customer AI before/at first authorized manual send. Idempotent."""
    if not actor_user_id or not str(actor_user_id).strip():
        raise ValueError("authenticated actor_user_id required")
    if not conversation_id or not user_id:
        raise ValueError("conversation_id and user_id required")

    channel = (source_channel or "").strip().lower() or None
    control_epoch: int | None = None
    wa_changed = False
    already_active = False

    if session is not None and tenant_id and (channel == SOURCE_CHANNEL_WHATSAPP_CLOUD or channel is None):
        wa_changed, control_epoch = _pause_whatsapp_cloud(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            actor_user_id=actor_user_id,
        )
        if control_epoch is not None and not wa_changed:
            already_active = True
        if control_epoch is not None:
            channel = SOURCE_CHANNEL_WHATSAPP_CLOUD

    # Firestore / Meta social path always — same SoT used by Live Chat AI guards.
    # WA Cloud may also have a Firestore mirror; dual write is intentional when both exist.
    try:
        await _pause_firestore(
            conversation_id=conversation_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
            operator_name=operator_name,
        )
    except ValueError:
        # Conversation may be WA-Cloud-only (no Firestore doc yet).
        if control_epoch is None:
            raise

    activated = wa_changed or not already_active
    audit_recorded = False
    if session is not None and tenant_id and request_id:
        row = CustomerRequestsRepository(session).get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise PermissionError("request_not_found_for_tenant")
        row.manual_mode_conversation_ref = conversation_id
        row.updated_at = _now()
        audit_recorded = _record_audit_once(
            session,
            tenant_id=tenant_id,
            request_id=request_id,
            actor_user_id=actor_user_id,
            event_type=EVENT_MANUAL_PAUSE,
            idempotency_key=f"pause:{request_id}:{conversation_id}",
            payload={
                "conversation_id": conversation_id,
                "channel": channel,
                "control_epoch": control_epoch,
                "activated": activated,
                "at": _now().isoformat(),
            },
        )

    return ManualModeResult(
        conversation_id=conversation_id,
        activated=activated,
        already_active=already_active and not wa_changed,
        control_epoch=control_epoch,
        channel=channel,
        audit_recorded=audit_recorded,
    )


async def resume_manual_mode(
    *,
    conversation_id: str,
    user_id: str,
    actor_user_id: str,
    tenant_id: str | None = None,
    request_id: str | None = None,
    source_channel: str | None = None,
    session: Session | None = None,
) -> ManualModeResult:
    """Clear manual pause (Resume AI). Idempotent. Never auto-invoked."""
    if not actor_user_id or not str(actor_user_id).strip():
        raise ValueError("authenticated actor_user_id required")

    channel = (source_channel or "").strip().lower() or None
    control_epoch: int | None = None
    wa_changed = False
    already_active_ai = False

    if session is not None and tenant_id and (channel == SOURCE_CHANNEL_WHATSAPP_CLOUD or channel is None):
        wa_changed, control_epoch = _resume_whatsapp_cloud(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            actor_user_id=actor_user_id,
        )
        if control_epoch is not None and not wa_changed:
            already_active_ai = True
        if control_epoch is not None:
            channel = SOURCE_CHANNEL_WHATSAPP_CLOUD

    try:
        await _resume_firestore(conversation_id=conversation_id, user_id=user_id)
    except ValueError:
        if control_epoch is None:
            raise

    activated = False  # resume clears mode
    audit_recorded = False
    if session is not None and tenant_id and request_id:
        row = CustomerRequestsRepository(session).get_for_tenant(tenant_id=tenant_id, request_id=request_id)
        if row is None:
            raise PermissionError("request_not_found_for_tenant")
        row.manual_mode_conversation_ref = None
        row.updated_at = _now()
        audit_recorded = _record_audit_once(
            session,
            tenant_id=tenant_id,
            request_id=request_id,
            actor_user_id=actor_user_id,
            event_type=EVENT_MANUAL_RESUME,
            idempotency_key=f"resume:{request_id}:{conversation_id}",
            payload={
                "conversation_id": conversation_id,
                "channel": channel,
                "control_epoch": control_epoch,
                "at": _now().isoformat(),
            },
        )

    return ManualModeResult(
        conversation_id=conversation_id,
        activated=activated,
        already_active=already_active_ai,
        control_epoch=control_epoch,
        channel=channel,
        audit_recorded=audit_recorded,
    )
