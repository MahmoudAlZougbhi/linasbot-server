"""
Post-booking session rating: prompt user on WhatsApp (numbered 1–5) and log analytics.
Uses the same adapter as the rest of the bot (MontyMobile send_button_message falls back to text).
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import config
from services.analytics_events import analytics
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

SESSION_RATING_ENABLED = os.getenv("SESSION_RATING_AFTER_BOOKING", "true").strip().lower() == "true"
SESSION_RATING_DELAY_SECONDS = float(os.getenv("SESSION_RATING_DELAY_SECONDS", "5"))
_rating_prompt_inflight: set[str] = set()


def _parse_star_from_user_text(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None
    arabic_map = str.maketrans("١٢٣٤٥٦٧٨٩٠", "1234567890")
    t = raw.translate(arabic_map)
    compact = re.sub(r"\s+", "", t)
    m = re.search(r"(?:rating_)(\d)$", compact, re.I)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 5 else None
    m2 = re.match(r"^(\d)$", compact)
    if m2:
        n = int(m2.group(1))
        return n if 1 <= n <= 5 else None
    if compact and compact[0] in "12345":
        if len(compact) == 1:
            return int(compact[0])
        if not compact[1].isdigit():
            return int(compact[0])
    return None


def _build_rating_prompt_body(lang: str) -> str:
    if (lang or "").lower().startswith("en"):
        return (
            "How was your experience with our assistant? Please reply with a number 1–5 "
            "(1 = poor, 5 = excellent).\n\n"
            "كيف كانت تجربتك مع المساعد؟ أرسل رقم من ١ ل٥ (١ ضعيف — ٥ ممتاز)."
        )
    return (
        "كيف كانت تجربتك مع المساعد الذكي؟\n"
        "أرسل رقمًا من ١ إلى ٥ (١ ضعيف — ٥ ممتاز).\n\n"
        "How was your experience? Reply with a number 1–5 (1 = poor, 5 = excellent)."
    )


async def try_handle_session_rating_reply(user_id: str, user_input_text: str, adapter: Any) -> bool:
    """If user is awaiting rating prompt, parse 1–5 and log. Returns True if handled."""
    ud = config.user_data_whatsapp.get(user_id) or {}
    if not ud.get("awaiting_session_rating"):
        return False
    stars = _parse_star_from_user_text(user_input_text)
    if stars is None:
        return False
    conv_id = ud.get("current_conversation_id")
    try:
        analytics.log_session_rating(user_id, stars, conversation_id=conv_id)
    except Exception as e:
        print(f"WARNING: log_session_rating: {e}")
    ud["awaiting_session_rating"] = False
    ud.pop("session_rating_prompt_sent_at", None)
    await adapter.send_text_message(
        user_id,
        "شكراً لتقييمك! 🌷\nThank you for your feedback!",
    )
    return True


async def schedule_session_rating_prompt_after_booking(user_id: str) -> None:
    if not SESSION_RATING_ENABLED:
        return
    if user_id in _rating_prompt_inflight:
        return
    _rating_prompt_inflight.add(user_id)
    try:
        try:
            await asyncio.sleep(SESSION_RATING_DELAY_SECONDS)
        except asyncio.CancelledError:
            return

        if config.user_in_human_takeover_mode.get(user_id, False):
            return

        ud = config.user_data_whatsapp.get(user_id) or {}
        conv_id = ud.get("current_conversation_id")
        if ud.get("session_rating_prompt_sent_conv") == conv_id and ud.get("awaiting_session_rating"):
            return

        adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
        lang = ud.get("user_preferred_lang") or "ar"
        body = _build_rating_prompt_body(lang)
        buttons = [
            {"label": "1 ⭐"},
            {"label": "2 ⭐⭐"},
            {"label": "3 ⭐⭐⭐"},
            {"label": "4 ⭐⭐⭐⭐"},
            {"label": "5 ⭐⭐⭐⭐⭐"},
        ]
        if hasattr(adapter, "send_button_message"):
            await adapter.send_button_message(user_id, body, buttons)
        else:
            lines = "\n".join(f"{i}. {b['label']}" for i, b in enumerate(buttons, 1))
            await adapter.send_text_message(user_id, f"{body}\n\n{lines}")
        ud["awaiting_session_rating"] = True
        ud["session_rating_prompt_sent_conv"] = conv_id
        ud["session_rating_prompt_sent_at"] = __import__("datetime").datetime.now().isoformat()
    except Exception as e:
        print(f"WARNING: schedule_session_rating_prompt_after_booking: {e}")
    finally:
        _rating_prompt_inflight.discard(user_id)
