"""Core logic for processing user input and generating bot responses.

Helpers live in sibling modules; `_process_and_respond` is split into phases.
"""

from __future__ import annotations

from typing import Any

from services.brain.inbound.text_handlers_respond_ctx import bootstrap_process_respond_ctx
from services.brain.inbound.text_handlers_respond_intent import (
    _build_out_of_scope_reply,
    _is_out_of_business_scope_query,
    _is_price_intent,
)
from services.brain.inbound.text_handlers_respond_keywords import (
    ASK_ONE_BY_ONE_ACTIONS,
    BRIEF_REPLY_ACTIONS,
    PRICE_INTENT_KEYWORDS,
)
from services.brain.inbound.text_handlers_respond_phase1 import text_handlers_respond_phase1
from services.brain.inbound.text_handlers_respond_phase2 import text_handlers_respond_phase2
from services.brain.inbound.text_handlers_respond_reply import (
    _apply_turn_by_turn_policy,
    _handle_published_cm_runtime,
    _reply_offers_handover_confirmation,
    _user_explicitly_requests_human_agent,
)

_PHASE_HALT = "_PHASE_HALT"

_PROCESS_PHASES = (
    text_handlers_respond_phase1,
    text_handlers_respond_phase2,
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
    bootstrap_process_respond_ctx(ctx)
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
    "_build_out_of_scope_reply",
    "_handle_published_cm_runtime",
    "_is_out_of_business_scope_query",
    "_is_price_intent",
    "_process_and_respond",
    "_reply_offers_handover_confirmation",
    "_user_explicitly_requests_human_agent",
]
