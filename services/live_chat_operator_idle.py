"""Resume AI when nobody is viewing a paused Live Chat thread."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.live_chat_contracts import UTC, utc_now

OPERATOR_IDLE_RESUME_SECONDS = 300
IDLE_RESUME_ACTOR = "system-idle-resume"


def parse_idle_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def should_auto_resume_ai(
    *,
    human_takeover_active: bool,
    operator_viewed_at: Any = None,
    last_activity: Any = None,
    now: datetime | None = None,
) -> bool:
    """True when takeover is on and nobody has viewed the thread recently."""
    if not human_takeover_active:
        return False
    now_utc = now or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    clock = parse_idle_timestamp(operator_viewed_at) or parse_idle_timestamp(last_activity)
    if clock is None:
        return True
    return (now_utc - clock).total_seconds() >= OPERATOR_IDLE_RESUME_SECONDS


async def auto_resume_if_operator_idle(
    *,
    conv_data: dict[str, Any],
    user_id: str,
    conversation_id: str,
    tenant_id: str | None,
    source_channel: str | None,
) -> bool:
    """Clear operator pause when the thread has been idle. Returns True if AI was resumed."""
    if not should_auto_resume_ai(
        human_takeover_active=bool(conv_data.get("human_takeover_active")),
        operator_viewed_at=conv_data.get("operator_viewed_at"),
        last_activity=conv_data.get("escalation_time")
        or conv_data.get("last_updated")
        or conv_data.get("last_activity"),
    ):
        return False

    tid = str(tenant_id).strip() if tenant_id else None
    print(f"[handle_message] INFO: operator idle — auto-resuming AI for conversation {conversation_id}")
    from services.live_chat_operator_pause_session import live_chat_manual_mode_db_session
    from services.requests.manual_mode import resume_manual_mode

    with live_chat_manual_mode_db_session(
        user_id=user_id,
        tenant_id=tid,
        source_channel=source_channel,
    ) as (session, channel):
        await resume_manual_mode(
            conversation_id=conversation_id,
            user_id=user_id,
            actor_user_id=IDLE_RESUME_ACTOR,
            tenant_id=tid,
            source_channel=channel,
            session=session,
        )
    try:
        import asyncio

        from services.live_chat_service import live_chat_service

        live_chat_service.invalidate_cache()
        asyncio.create_task(live_chat_service._refresh_index_for_conversation(user_id, conversation_id))
    except Exception as idx_err:
        print(f"⚠️ idle resume index refresh: {idx_err}")
    return True
