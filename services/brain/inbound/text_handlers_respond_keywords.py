"""Intent/reply constants still used after Terra authors a reply (post-AI shaping)."""

from __future__ import annotations

ASK_ONE_BY_ONE_ACTIONS = {
    "ask_for_details_for_booking",
    "ask_for_service_type",
    "ask_for_details",
    "ask_for_tattoo_photo",
    "ask_clarification",
}

BRIEF_REPLY_ACTIONS = {
    "answer_question",
    "normal_chat",
    "provide_info",
    "unknown_query",
    "tool_call",
    "check_customer_status",
}

INTERROGATIVE_PREFIXES = (
    "شو",
    "شو ",
    "أي",
    "اي",
    "هل",
    "ممكن",
    "فينا",
    "قديش",
    "كم",
    "what",
    "which",
    "could",
    "can",
    "where",
    "when",
    "who",
    "how",
)
