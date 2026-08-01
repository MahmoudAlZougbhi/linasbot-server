"""
After the Post Session Feedback WhatsApp template is sent, accept a 1–5 star reply
(text or quick-reply title), log analytics, and clear awaiting state.
Separate from session_rating_service (after-booking bot prompt).
"""

from __future__ import annotations

import datetime
from typing import Any

import config
from config import ensure_conversation_state
from services.session_rating_service import _parse_star_from_user_text
from utils.utils import get_canonical_user_id_and_phone

# How long we treat the customer as "replying to" the feedback template (hours).
_POST_SESSION_FEEDBACK_RATING_TTL_HOURS = int(
    __import__("os").getenv("POST_SESSION_FEEDBACK_RATING_TTL_HOURS", "336") or "336"
)


def _ctx_expired(since_iso: str | None) -> bool:
    if not since_iso:
        return False
    try:
        raw = str(since_iso).strip().replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        age = datetime.datetime.now() - dt
        return age.total_seconds() > _POST_SESSION_FEEDBACK_RATING_TTL_HOURS * 3600
    except Exception:
        return False


def mark_awaiting_post_session_feedback_after_send(
    phone: str | None,
    appointment_id: Any | None = None,
    reference_date: str | None = None,
    smart_message_id: str | None = None,
) -> None:
    """Call after a real Post Session Feedback template send succeeds."""
    raw = str(phone or "").strip()
    if not raw:
        return
    uid, _norm = get_canonical_user_id_and_phone(raw, raw)
    if not uid:
        return
    ud = config.user_data_whatsapp[uid]
    ensure_conversation_state(ud)
    ud["awaiting_post_session_feedback_rating"] = True
    ud["post_session_feedback_rating_context"] = {
        "since": datetime.datetime.now().isoformat(),
        "appointment_id": appointment_id,
        "reference_date": str(reference_date).strip() if reference_date else None,
        "smart_message_id": str(smart_message_id).strip() if smart_message_id else None,
    }


async def try_handle_post_session_feedback_reply(user_id: str, user_input_text: str, adapter: Any) -> bool:
    """If user is awaiting post-session star reply, parse 1–5, log, thank, return True."""
    ud = config.user_data_whatsapp.get(user_id) or {}
    if not ud.get("awaiting_post_session_feedback_rating"):
        return False
    ctx = ud.get("post_session_feedback_rating_context") or {}
    if _ctx_expired(ctx.get("since")):
        ud["awaiting_post_session_feedback_rating"] = False
        ud.pop("post_session_feedback_rating_context", None)
        return False
    stars = _parse_star_from_user_text(user_input_text)
    if stars is None:
        return False
    conv_id = ud.get("current_conversation_id")
    try:
        from services.analytics_events import analytics

        analytics.log_post_session_feedback_rating(
            user_id=user_id,
            stars=stars,
            conversation_id=conv_id,
            appointment_id=ctx.get("appointment_id"),
            reference_date=ctx.get("reference_date"),
            raw_reply=str(user_input_text or "").strip()[:240],
            smart_message_id=ctx.get("smart_message_id"),
        )
    except Exception as e:
        print(f"WARNING: log_post_session_feedback_rating: {e}")
    ud["awaiting_post_session_feedback_rating"] = False
    ud.pop("post_session_feedback_rating_context", None)
    await adapter.send_text_message(
        user_id,
        "شكراً لتقييمك! 🌷\nThank you for your feedback!",
    )
    return True
