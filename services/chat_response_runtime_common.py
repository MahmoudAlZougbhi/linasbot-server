"""Shared imports and sentinels for split get_bot_chat_response runtime."""

from __future__ import annotations

import asyncio
import datetime
import json
import re
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject

import config
from prompt_templates import CUSTOMER_STATUS_TOKEN
from services import api_integrations
from services.chat_response_service_appointments import (
    _appointment_numeric_id,
    _bot_reply_claims_bulk_all_appointments_updated,
    _bot_reply_claims_pause_lifted_or_resumed,
    _build_live_crm_appointments_snapshot,
    _build_multi_appointment_reschedule_hint,
    _build_pause_resume_execution_guardrail,
    _count_live_reschedule_row_total,
    _operational_context_promises_imminent_appointment_update,
    _status_requests_available,
    _user_intent_resume_paused_appointment,
    _user_message_is_acknowledgment_only,
)
from services.chat_response_service_booking_args import (
    _bot_reply_claims_completed_booking,
    _extract_booking_args_from_gpt_raw,
    _extract_submit_booking_failure_details,
    _infer_service_id_from_leak,
    _latest_successful_update_date_from_tool_rounds,
    _parse_gpt_response_json,
    _partial_paused_date_update_reply,
    _resolve_branch_id_from_leak,
)
from services.chat_response_service_booking_name import (
    _coerce_body_part_ids_from_gpt_booking_args,
    _missing_body_part_booking_prompt,
    _sanitize_submit_booking_tool_for_model,
    _try_recover_create_appointment_from_auxiliary_gpt_json,
)
from services.chat_response_service_booking_resolve import (
    _fetch_customer_file_summary_for_ai,
    _resolve_machine_for_booking,
    _user_explicitly_requests_machine_change,
)
from services.chat_response_service_constants import (
    _SUBMIT_BOOKING_TOOL_HINT_TECHNICAL,
    BOOKING_TZ,
    FINAL_RESPONSE_MODEL,
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    ORCHESTRATION_MODEL,
    _normalize_body_part_ids,
    _safe_int,
)
from services.chat_response_service_gpt_parse import (
    _apply_inferred_name_from_user_bundle,
    _fix_misassigned_tattoo_service_for_hair_booking,
    _prune_redundant_booking_questions_when_name_from_bundle,
    _try_infer_body_part_ids_from_conversation,
)
from services.chat_response_service_pause import (
    _booking_submit_payload_complete_for_execution,
    _bot_reply_claims_completed_appointment_update,
    _contains_arabic_script,
    _extract_direct_submit_booking_args_from_user_message,
    _merge_explicit_user_booking_args,
    _ordered_paused_appointments_from_snapshot,
    _resolve_user_chosen_paused_appointment_id,
    is_price_related_question,
)
from services.chat_response_service_pricing import (
    _build_exact_pricing_reply,
    _finalize_create_appointment_payload_for_api,
    _get_body_part_required_service_ids,
    _infer_service_id_for_pricing,
    _merge_pricing_args_with_booking_state,
    _pricing_missing_details_reply,
    _remember_booking_selection,
    _reply_from_submit_booking_tool,
)
from services.chat_response_service_profile import (
    _clinic_holiday_calendar_block,
    _extract_customer_appointments_list,
    _is_paused_like_appointment_status,
    _normalize_arabic_reply,
    _normalize_profile_gender,
    _record_tool_round_trip,
    _update_current_conversation_customer_info,
    _update_profile_name_in_firestore,
    _validate_profile_name,
)
from services.gender_recognition_service import get_gender_from_gpt
from services.llm_core_service import client
from services.model_pricing import compute_cost_from_usage as _compute_cost_from_usage
from services.moderation_service import check_rate_limits, get_rate_limit_response
from services.product_features import LEGACY_BOOKING_TOOL_NAMES
from utils.appointment_slot_rules import (
    extract_appointment_booking_fields,
    find_appointment_row_in_check_next_payload,
    parse_normalized_api_datetime,
    validate_booking_slot,
)
from utils.datetime_utils import (
    align_datetime_to_day_reference,
    datetime_from_ai_date_components,
    detect_appointment_inquiry_intent,
    detect_bulk_reschedule_all_intent,
    detect_existing_appointment_edit_intent,
    detect_last_weekday_intent_from_user_text,
    detect_reschedule_intent,
    format_clinic_calendar_anchor,
    next_future_datetime_matching_weekday,
    now_in_bot_tz,
    parse_datetime_flexible,
)
from utils.utils import get_openai_tools_schema, get_system_instruction

LOOP_CONTINUE = object()

__all__ = [
    "Any",
    "BOOKING_TZ",
    "CUSTOMER_STATUS_TOKEN",
    "ChatCompletionMessageParam",
    "ChatCompletionToolParam",
    "FINAL_RESPONSE_MODEL",
    "HAIR_REMOVAL_MACHINE_IDS",
    "LASER_HAIR_REMOVAL_SERVICE_IDS",
    "LEGACY_BOOKING_TOOL_NAMES",
    "LOOP_CONTINUE",
    "ORCHESTRATION_MODEL",
    "ResponseFormatJSONObject",
    "_SUBMIT_BOOKING_TOOL_HINT_TECHNICAL",
    "_apply_inferred_name_from_user_bundle",
    "_appointment_numeric_id",
    "_booking_submit_payload_complete_for_execution",
    "_bot_reply_claims_bulk_all_appointments_updated",
    "_bot_reply_claims_completed_appointment_update",
    "_bot_reply_claims_completed_booking",
    "_bot_reply_claims_pause_lifted_or_resumed",
    "_build_exact_pricing_reply",
    "_build_live_crm_appointments_snapshot",
    "_build_multi_appointment_reschedule_hint",
    "_build_pause_resume_execution_guardrail",
    "_clinic_holiday_calendar_block",
    "_coerce_body_part_ids_from_gpt_booking_args",
    "_compute_cost_from_usage",
    "_contains_arabic_script",
    "_count_live_reschedule_row_total",
    "_extract_booking_args_from_gpt_raw",
    "_extract_customer_appointments_list",
    "_extract_direct_submit_booking_args_from_user_message",
    "_extract_submit_booking_failure_details",
    "_fetch_customer_file_summary_for_ai",
    "_finalize_create_appointment_payload_for_api",
    "_fix_misassigned_tattoo_service_for_hair_booking",
    "_get_body_part_required_service_ids",
    "_infer_service_id_for_pricing",
    "_infer_service_id_from_leak",
    "_is_paused_like_appointment_status",
    "_latest_successful_update_date_from_tool_rounds",
    "_merge_explicit_user_booking_args",
    "_merge_pricing_args_with_booking_state",
    "_missing_body_part_booking_prompt",
    "_normalize_arabic_reply",
    "_normalize_body_part_ids",
    "_normalize_profile_gender",
    "_operational_context_promises_imminent_appointment_update",
    "_ordered_paused_appointments_from_snapshot",
    "_parse_gpt_response_json",
    "_partial_paused_date_update_reply",
    "_pricing_missing_details_reply",
    "_prune_redundant_booking_questions_when_name_from_bundle",
    "_record_tool_round_trip",
    "_remember_booking_selection",
    "_reply_from_submit_booking_tool",
    "_resolve_branch_id_from_leak",
    "_resolve_machine_for_booking",
    "_resolve_user_chosen_paused_appointment_id",
    "_safe_int",
    "_sanitize_submit_booking_tool_for_model",
    "_status_requests_available",
    "_try_infer_body_part_ids_from_conversation",
    "_try_recover_create_appointment_from_auxiliary_gpt_json",
    "_update_current_conversation_customer_info",
    "_update_profile_name_in_firestore",
    "_user_explicitly_requests_machine_change",
    "_user_intent_resume_paused_appointment",
    "_user_message_is_acknowledgment_only",
    "_validate_profile_name",
    "align_datetime_to_day_reference",
    "annotations",
    "api_integrations",
    "asyncio",
    "cast",
    "check_rate_limits",
    "client",
    "config",
    "datetime",
    "datetime_from_ai_date_components",
    "detect_appointment_inquiry_intent",
    "detect_bulk_reschedule_all_intent",
    "detect_existing_appointment_edit_intent",
    "detect_last_weekday_intent_from_user_text",
    "detect_reschedule_intent",
    "extract_appointment_booking_fields",
    "find_appointment_row_in_check_next_payload",
    "format_clinic_calendar_anchor",
    "get_gender_from_gpt",
    "get_openai_tools_schema",
    "get_rate_limit_response",
    "get_system_instruction",
    "is_price_related_question",
    "json",
    "next_future_datetime_matching_weekday",
    "now_in_bot_tz",
    "parse_datetime_flexible",
    "parse_normalized_api_datetime",
    "re",
    "validate_booking_slot",
]
