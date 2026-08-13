"""Bootstrap shared services for `_process_and_respond` phase pipeline."""

from __future__ import annotations

from typing import Any


def _lazy_bindings() -> dict[str, Any]:
    """Import-heavy bindings shared by inline webhook and Redis worker paths."""
    from handlers.text_handlers_respond_intent import (
        _build_out_of_scope_reply,
        _classify_booking_offer_confirmation_reply,
        _flow_meta_has_crm_booking_confirmation,
        _is_out_of_clinic_scope_query,
        _is_price_intent,
        _parse_tool_round_bot_returned,
        _reply_claims_booking_done,
    )
    from handlers.text_handlers_respond_reply import (
        _apply_turn_by_turn_policy,
        _handle_published_cm_runtime,
        _reply_offers_handover_confirmation,
        _user_explicitly_requests_human_agent,
    )
    from services.api_integrations import log_report_event
    from services.chat_response_service import get_bot_chat_response
    from services.conversation_router import (
        ASK_CLARIFICATION_TEMPLATES,
        FALLBACK_TEMPLATES,
        GREETING_TEMPLATES,
        get_gender_from_message,
        route,
    )
    from services.dynamic_messages_service import get_dynamic_message
    from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction
    from services.language_detection_service import language_detection_service
    from services.local_qa_service import local_qa_service
    from services.social_contact_routing import route_social_contact_request
    from services.user_persistence_service import user_persistence
    from utils.datetime_intents import detect_reschedule_intent
    from utils.utils import (
        count_tokens,
        get_canonical_user_id_and_phone,
        get_conversation_context_for_gpt,
        get_conversation_last_ai_response_at,
        get_firestore_db,
        get_last_bot_message_for_gpt_context,
        get_system_instruction,
        is_post_takeover_escalation_cooldown,
        notify_human_on_whatsapp,
        save_conversation_message_to_firestore,
        save_for_training_conversation_log,
        set_post_takeover_escalation_cooldown,
        update_dashboard_metric_in_firestore,
    )

    def _is_social_channel(channel: str | None) -> bool:
        return str(channel or "").strip().lower() in {"instagram", "facebook"}

    return {
        "ASK_CLARIFICATION_TEMPLATES": ASK_CLARIFICATION_TEMPLATES,
        "FALLBACK_TEMPLATES": FALLBACK_TEMPLATES,
        "GREETING_TEMPLATES": GREETING_TEMPLATES,
        "_apply_turn_by_turn_policy": _apply_turn_by_turn_policy,
        "_build_out_of_scope_reply": _build_out_of_scope_reply,
        "_classify_booking_offer_confirmation_reply": _classify_booking_offer_confirmation_reply,
        "_flow_meta_has_crm_booking_confirmation": _flow_meta_has_crm_booking_confirmation,
        "_handle_published_cm_runtime": _handle_published_cm_runtime,
        "_is_out_of_clinic_scope_query": _is_out_of_clinic_scope_query,
        "_is_price_intent": _is_price_intent,
        "_parse_tool_round_bot_returned": _parse_tool_round_bot_returned,
        "_reply_claims_booking_done": _reply_claims_booking_done,
        "_reply_offers_handover_confirmation": _reply_offers_handover_confirmation,
        "_user_explicitly_requests_human_agent": _user_explicitly_requests_human_agent,
        "count_tokens": count_tokens,
        "detect_reschedule_intent": detect_reschedule_intent,
        "get_bot_chat_response": get_bot_chat_response,
        "get_canonical_user_id_and_phone": get_canonical_user_id_and_phone,
        "get_conversation_context_for_gpt": get_conversation_context_for_gpt,
        "get_conversation_last_ai_response_at": get_conversation_last_ai_response_at,
        "get_dynamic_message": get_dynamic_message,
        "get_firestore_db": get_firestore_db,
        "get_gender_from_message": get_gender_from_message,
        "get_last_bot_message_for_gpt_context": get_last_bot_message_for_gpt_context,
        "get_system_instruction": get_system_instruction,
        "is_flow_logging_enabled": is_flow_logging_enabled,
        "is_post_takeover_escalation_cooldown": is_post_takeover_escalation_cooldown,
        "is_social_channel": _is_social_channel,
        "language_detection_service": language_detection_service,
        "local_qa_service": local_qa_service,
        "log_interaction": log_interaction,
        "log_report_event": log_report_event,
        "notify_human_on_whatsapp": notify_human_on_whatsapp,
        "route_social_contact_request": route_social_contact_request,
        "router_route": route,
        "save_conversation_message_to_firestore": save_conversation_message_to_firestore,
        "save_for_training_conversation_log": save_for_training_conversation_log,
        "set_post_takeover_escalation_cooldown": set_post_takeover_escalation_cooldown,
        "update_dashboard_metric_in_firestore": update_dashboard_metric_in_firestore,
        "user_persistence": user_persistence,
    }


def bootstrap_process_respond_ctx(ctx: dict[str, Any]) -> None:
    """Populate ctx with services required by phase 1+.

    Worker and inline Meta paths call `_process_and_respond` directly; they do not
    pass through `handle_message` imports. Idempotent per key.
    """
    for key, value in _lazy_bindings().items():
        if ctx.get(key) is None:
            ctx[key] = value


__all__ = ["bootstrap_process_respond_ctx"]
