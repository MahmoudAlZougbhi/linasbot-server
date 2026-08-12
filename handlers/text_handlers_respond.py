"""Core logic for processing user input and generating bot responses.

Helpers live in sibling modules; `_process_and_respond` is split into phases.
"""

from __future__ import annotations

from typing import Any

from handlers.text_handlers_respond_intent import (
    _booking_not_confirmed_safe_reply,
    _build_out_of_scope_reply,
    _classify_booking_offer_confirmation_reply,
    _flow_meta_has_crm_booking_confirmation,
    _is_out_of_clinic_scope_query,
    _is_price_intent,
    _parse_tool_round_bot_returned,
    _reply_claims_booking_done,
)
from handlers.text_handlers_respond_keywords import (
    ASK_ONE_BY_ONE_ACTIONS,
    BRIEF_REPLY_ACTIONS,
    PRICE_INTENT_KEYWORDS,
)
from handlers.text_handlers_respond_phase1 import text_handlers_respond_phase1
from handlers.text_handlers_respond_phase2 import text_handlers_respond_phase2
from handlers.text_handlers_respond_phase3 import text_handlers_respond_phase3
from handlers.text_handlers_respond_phase4 import text_handlers_respond_phase4
from handlers.text_handlers_respond_phase5 import text_handlers_respond_phase5
from handlers.text_handlers_respond_phase6 import text_handlers_respond_phase6
from handlers.text_handlers_respond_phase7 import text_handlers_respond_phase7
from handlers.text_handlers_respond_phase8 import text_handlers_respond_phase8
from handlers.text_handlers_respond_phase9 import text_handlers_respond_phase9
from handlers.text_handlers_respond_phase10 import text_handlers_respond_phase10
from handlers.text_handlers_respond_phase11 import text_handlers_respond_phase11
from handlers.text_handlers_respond_phase12 import text_handlers_respond_phase12
from handlers.text_handlers_respond_reply import (
    _apply_turn_by_turn_policy,
    _handle_published_cm_runtime,
    _reply_offers_handover_confirmation,
    _user_explicitly_requests_human_agent,
)

_PHASE_HALT = "_PHASE_HALT"

_PROCESS_PHASES = (
    text_handlers_respond_phase1,
    text_handlers_respond_phase2,
    text_handlers_respond_phase3,
    text_handlers_respond_phase4,
    text_handlers_respond_phase5,
    text_handlers_respond_phase6,
    text_handlers_respond_phase7,
    text_handlers_respond_phase8,
    text_handlers_respond_phase9,
    text_handlers_respond_phase10,
    text_handlers_respond_phase11,
    text_handlers_respond_phase12,
)


async def _process_and_respond(
    user_id: str,
    user_name: str,
    user_input_to_process: str,
    user_data: dict,
    send_message_func: Any,
    send_action_func: Any,
    user_image_base64: str | None = None,
    user_image_format: str = "jpeg",
) -> Any:
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    ctx: dict[str, Any] = {
        "user_id": user_id,
        "user_name": user_name,
        "user_input_to_process": user_input_to_process,
        "user_data": user_data,
        "send_message_func": send_message_func,
        "send_action_func": send_action_func,
        "user_image_base64": user_image_base64,
        "user_image_format": user_image_format,
    }
    for phase in _PROCESS_PHASES:
        result = await phase(ctx)
        if result == _PHASE_HALT:
            return None
    return None


__all__ = [
    "ASK_ONE_BY_ONE_ACTIONS",
    "BRIEF_REPLY_ACTIONS",
    "PRICE_INTENT_KEYWORDS",
    "_apply_turn_by_turn_policy",
    "_booking_not_confirmed_safe_reply",
    "_build_out_of_scope_reply",
    "_classify_booking_offer_confirmation_reply",
    "_flow_meta_has_crm_booking_confirmation",
    "_handle_published_cm_runtime",
    "_is_out_of_clinic_scope_query",
    "_is_price_intent",
    "_parse_tool_round_bot_returned",
    "_process_and_respond",
    "_reply_claims_booking_done",
    "_reply_offers_handover_confirmation",
    "_user_explicitly_requests_human_agent",
]
