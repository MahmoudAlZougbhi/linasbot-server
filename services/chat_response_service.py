"""Legacy GPT chat-response path. Helpers and runtime live in sibling modules."""

from __future__ import annotations

from services.chat_response_runtime import get_bot_chat_response
from services.chat_response_service_gpt_parse import _is_placeholder_booking_customer_name
from services.chat_response_service_profile import _extract_customer_appointments_list

__all__ = [
    "get_bot_chat_response",
    "_extract_customer_appointments_list",
    "_is_placeholder_booking_customer_name",
]
