"""Schedule Smart Follow-Up after Meta social AI replies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.requests.constants import SOURCE_CHANNEL_FACEBOOK_MESSENGER, SOURCE_CHANNEL_INSTAGRAM_DM
from services.smart_followup.constants import QUALIFYING_SOCIAL_ACTIONS
from services.smart_followup.hooks import schedule_after_ai_reply
from services.social_contact_routing_detect import is_social_channel


def _social_followup_channel(raw_channel: str | None) -> str | None:
    ch = str(raw_channel or "").strip().lower()
    if ch == "instagram":
        return SOURCE_CHANNEL_INSTAGRAM_DM
    if ch == "facebook":
        return SOURCE_CHANNEL_FACEBOOK_MESSENGER
    return None


def maybe_schedule_social_followup_after_ai_reply(
    *,
    user_id: str,
    user_name: str,
    user_data: dict[str, Any],
    conversation_id: str | None,
    action: str | None,
    sent_reply: str | None,
    source_message_id: str | None = None,
) -> dict[str, Any] | None:
    if not conversation_id or not sent_reply or not str(sent_reply).strip():
        return None
    if action not in QUALIFYING_SOCIAL_ACTIONS:
        return None
    if action in {"human_handover", "human_handover_confirmed", "human_handover_initial_ask"}:
        return None

    channel = _social_followup_channel(user_data.get("channel"))
    if channel is None or not is_social_channel(user_data.get("channel")):
        return None

    tenant_id = str(user_data.get("tenant_id") or "").strip()
    if not tenant_id:
        return None

    binding_id = str(user_data.get("meta_binding_id") or "").strip()
    asset_id = str(user_data.get("meta_account_id") or "").strip()
    sender_id = str(user_data.get("social_sender_id") or "").strip()
    if not binding_id or not asset_id or not sender_id:
        return None

    last_inbound = user_data.get("last_user_message_at")
    if isinstance(last_inbound, datetime):
        last_inbound_iso = last_inbound.astimezone(UTC).isoformat()
    elif last_inbound is not None:
        last_inbound_iso = str(last_inbound)
    else:
        last_inbound_iso = datetime.now(UTC).isoformat()

    trigger_ref = str(
        source_message_id or user_data.get("_source_message_id") or f"social:{conversation_id}:{last_inbound_iso}"
    )
    sent_at = datetime.now(UTC)
    channel_context = {
        "user_id": user_id,
        "profile_name": user_name,
        "social_sender_id": sender_id,
        "asset_id": asset_id,
        "meta_binding_id": binding_id,
        "meta_app_key": str(user_data.get("meta_app_key") or ""),
        "trigger_ref": trigger_ref,
        "last_inbound_at": last_inbound_iso,
    }

    from db.session import whatsapp_session

    try:
        with whatsapp_session() as session:
            return schedule_after_ai_reply(
                session,
                tenant_id=tenant_id,
                channel=channel,
                connection_id=binding_id,
                conversation_id=conversation_id,
                trigger_outbound_intent_id=trigger_ref,
                control_epoch=1,
                trigger_ai_sent_at=sent_at,
                channel_context=channel_context,
            )
    except Exception as exc:
        from services.whatsapp_cloud.observability import emit_wa_event

        emit_wa_event("smart_followup_schedule_failed", error=type(exc).__name__, channel=channel)
        return {"scheduled": False, "reason": "schedule_failed"}
