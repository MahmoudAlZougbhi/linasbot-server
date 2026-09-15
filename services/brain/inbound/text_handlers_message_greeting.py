from __future__ import annotations

# Greeting + combine-lock helpers for handle_message (LOC split).
import asyncio

from services.owner_copilot.dynamic_messages_service import get_dynamic_message

GREETING_INACTIVITY_SECONDS = 43200  # 12 hours

# Serialize append + epoch bump + create_task per user so two concurrent handle_message calls
# cannot both read the same _text_turn_epoch and schedule two waves with the same epoch (duplicate sends).
_combine_schedule_locks: dict[str, asyncio.Lock] = {}


def _combine_schedule_lock(user_id: str) -> asyncio.Lock:
    lock = _combine_schedule_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _combine_schedule_locks[user_id] = lock
    return lock


def _get_session_greeting_message(user_lang: str = "ar") -> str:
    """Greeting from published dynamic messages, then router templates."""
    dyn = get_dynamic_message("session_greeting_after_inactivity", user_lang)
    if dyn:
        return dyn
    try:
        from services.brain.conversation_router import GREETING_TEMPLATES

        return GREETING_TEMPLATES.get(user_lang, GREETING_TEMPLATES["ar"])
    except Exception:
        return "مرحباً! 😊 كيف فيني ساعدك اليوم؟"
