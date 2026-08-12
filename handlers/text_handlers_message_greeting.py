from __future__ import annotations

# Greeting + combine-lock helpers for handle_message (LOC split).
import asyncio
from typing import Any

from services.dynamic_messages_service import get_dynamic_message

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


def _extract_greeting_from_style_content(style_content: str) -> str:
    """Extract a user-facing greeting sentence from a style file content."""
    if not style_content:
        return ""
    lines = [ln.strip() for ln in str(style_content).splitlines() if ln.strip()]
    # Prefer explicit example bot lines first.
    for ln in lines:
        lower = ln.lower()
        if lower.startswith("bot:") or lower.startswith("assistant:"):
            candidate = ln.split(":", 1)[1].strip()
            if candidate:
                return candidate
    # Fallback: first non-heading/non-rule line.
    for ln in lines:
        if ln.startswith("#") or ln.startswith("-") or ln.lower().startswith("rule"):
            continue
        if len(ln) >= 8:
            return ln
    return ""


def _get_session_greeting_message(user_lang: str = "ar") -> str:
    """
    Load greeting from AI Setup style files (title contains 'greeting').
    Falls back to router greeting templates when no suitable content is found.
    """
    try:
        from services import content_files_service as cfs

        titles = cfs.get_titles_only("style") or []
        greeting_candidates = []
        for t in titles:
            title = str(t.get("title", ""))
            if "greeting" in title.lower() or "ترحيب" in title.lower():
                greeting_candidates.append(t)

        # Prefer file language match first.
        def _lang_score(t: Any) -> Any:
            lang = (t.get("language") or "").lower()
            if lang == user_lang:
                return 2
            if lang in ("", "ar", "general"):
                return 1
            return 0

        greeting_candidates.sort(key=_lang_score, reverse=True)
        for t in greeting_candidates:
            data = cfs.get_file("style", t.get("id", ""))
            if not data:
                continue
            extracted = _extract_greeting_from_style_content(data.get("content", ""))
            if extracted:
                return extracted
    except Exception as e:
        print(f"[handle_message] ⚠️ Failed loading greeting from content manager: {e}")

    # Try dynamic messages catalog first
    dyn = get_dynamic_message("session_greeting_after_inactivity", user_lang)
    if dyn:
        return dyn

    # Final fallback
    try:
        from services.conversation_router import GREETING_TEMPLATES

        return GREETING_TEMPLATES.get(user_lang, GREETING_TEMPLATES["ar"])
    except Exception:
        return "مرحباً! 😊 كيف فيني ساعدك اليوم؟"
