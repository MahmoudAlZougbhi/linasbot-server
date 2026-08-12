"""Failure flags, tokens, pricing sync, success return."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    Any,
    _bot_reply_claims_bulk_all_appointments_updated,
    _bot_reply_claims_completed_appointment_update,
    _bot_reply_claims_completed_booking,
    _bot_reply_claims_pause_lifted_or_resumed,
    _build_exact_pricing_reply,
    _compute_cost_from_usage,
    _count_live_reschedule_row_total,
    _extract_booking_args_from_gpt_raw,
    _extract_submit_booking_failure_details,
    _infer_service_id_for_pricing,
    _infer_service_id_from_leak,
    _latest_successful_update_date_from_tool_rounds,
    _missing_body_part_booking_prompt,
    _normalize_arabic_reply,
    _normalize_body_part_ids,
    _operational_context_promises_imminent_appointment_update,
    _partial_paused_date_update_reply,
    _pricing_missing_details_reply,
    _remember_booking_selection,
    _resolve_branch_id_from_leak,
    _safe_int,
    _user_message_is_acknowledgment_only,
    api_integrations,
    config,
    json,
)


async def finish_chat_response(ns: Any) -> Any:
    # Structured booking only: no same-day or text-based booking fallbacks.

    # User replied Ok/تمام after bot said it WILL update (e.g. "رح أعدّل موعد…") — model must not claim "تم تثبيت التعديل" without tools.
    if not ns.api_failure_reason and not ns.had_update_tool:
        ns._pending_update_promise = _operational_context_promises_imminent_appointment_update(ns.operational_context)
        if not ns._pending_update_promise:
            for ns._msg in reversed(ns.current_context_messages or []):
                if ns._msg.get("role") == "assistant":
                    ns._pending_update_promise = _operational_context_promises_imminent_appointment_update(
                        str(ns._msg.get("content") or "")
                    )
                    break
        if (
            _bot_reply_claims_completed_appointment_update(ns.parsed_response.get("bot_reply") or "")
            and _user_message_is_acknowledgment_only(ns.user_input)
            and ns._pending_update_promise
        ):
            ns.api_failure_reason = "update_claimed_without_tool_after_pending_promise"

    # Reschedule wording in user message + completion text but no update_appointment_date in this turn.
    if not ns.api_failure_reason and ns.tool_calls and not ns.had_update_tool and ns.is_reschedule_intent:
        if any(
            ns.m in ns._brl_flow
            for ns.m in (
                "تم تأجيل",
                "تمّ تأجيل",
                "تم التأجيل",
                "تم تعديل الموعد",
                "تمّ تعديل الموعد",
                "تم تغيير الموعد",
                "تم تحديث الموعد",
                "تم نقل الموعد",
                "صار موعدك",
                "أصبح موعدك",
                "rescheduled",
                "postponed your appointment",
                "moved your appointment",
                "appointment has been updated",
            )
        ):
            ns.api_failure_reason = "reschedule_claimed_without_update_appointment_date_tool"

    # Claims paused appointment was cleared / became active without a successful CRM update.
    ns._paused_date_changed_without_resume = (
        ns.update_appointment_date_success_count > 0 and ns.pause_resume_attempted and ns.pause_resume_success_count == 0
    )
    if (
        not ns.api_failure_reason
        and ns._paused_date_changed_without_resume
        and _bot_reply_claims_pause_lifted_or_resumed(ns.parsed_response.get("bot_reply") or "")
    ):
        ns.parsed_response["action"] = "answer_question"
        ns.parsed_response["bot_reply"] = _partial_paused_date_update_reply(
            ns.detected_language,
            _latest_successful_update_date_from_tool_rounds(ns.tool_round_trips),
        )

    if (
        not ns.api_failure_reason
        and ns.paused_followup_update_succeeded
        and not ns.paused_followup_available_action_requested
        and not ns._paused_date_changed_without_resume
    ):
        ns.api_failure_reason = "paused_update_missing_available_action_request"

    if (
        not ns.api_failure_reason
        and ns.paused_followup_update_succeeded
        and ns.pause_resume_success_count == 0
        and not ns._paused_date_changed_without_resume
    ):
        ns.api_failure_reason = "paused_update_completed_without_available_confirmation"

    if (
        not ns.api_failure_reason
        and ns.tool_calls
        and ns.had_update_tool
        and ns.pause_resume_success_count == 0
        and not ns._paused_date_changed_without_resume
        and _bot_reply_claims_pause_lifted_or_resumed(ns.parsed_response.get("bot_reply") or "")
    ):
        ns.api_failure_reason = "pause_resume_claimed_without_successful_resume_action"

    if (
        not ns.api_failure_reason
        and ns.tool_calls
        and not ns.had_update_tool
        and _bot_reply_claims_pause_lifted_or_resumed(ns.parsed_response.get("bot_reply") or "")
    ):
        ns.api_failure_reason = "pause_resume_claimed_without_update_appointment_date_tool"

    # If the model text claims a completed booking but never called create_appointment → handover signal.
    # Skip when reply is clearly an appointment *update* completion (handled above).
    if (
        not ns.api_failure_reason
        and ns.tool_calls
        and "create_appointment" not in ns.tool_names
        and "submit_booking_intent" not in ns.tool_names
        and not ns.recovered_create_appointment_ok
        and not _bot_reply_claims_completed_appointment_update(ns.parsed_response.get("bot_reply") or "")
    ):
        if _bot_reply_claims_completed_booking(ns.parsed_response.get("bot_reply") or ""):
            ns.tattoo_soft_recover = False
            try:
                ns.leaked_book = _extract_booking_args_from_gpt_raw(ns.gpt_raw_content or "")
                ns.inf_sid = _infer_service_id_from_leak(ns.leaked_book, ns.current_gender)
                ns.st = config.user_booking_state.get(ns.user_id) or {}
                ns.st_sid = _safe_int(ns.st.get("service_id"))
                ns.bp_leak = _normalize_body_part_ids(ns.leaked_book.get("body_part_ids"))
                ns.bp_state = _normalize_body_part_ids(ns.st.get("body_part_ids")) if ns.st_sid == ns.inf_sid else []
                if ns.inf_sid == 13 and 13 in ns.body_part_required_service_ids and not (ns.bp_leak or ns.bp_state):
                    ns.tattoo_soft_recover = True
                    ns.parsed_response["action"] = "ask_for_details_for_booking"
                    ns.parsed_response["bot_reply"] = _missing_body_part_booking_prompt(13, ns.detected_language)
                    ns.partial_state: dict[str, Any] = {"service_id": 13}
                    ns.bid = _resolve_branch_id_from_leak(ns.leaked_book)
                    if ns.bid is not None:
                        ns.partial_state["branch_id"] = ns.bid
                    ns.mid = _safe_int(ns.leaked_book.get("machine_id"))
                    if ns.mid is not None:
                        ns.partial_state["machine_id"] = ns.mid
                    _remember_booking_selection(ns.user_id, ns.partial_state)
                    if ns.detected_language in ("ar", "franco") and ns.parsed_response.get("bot_reply"):
                        ns.parsed_response["bot_reply"] = _normalize_arabic_reply(ns.parsed_response["bot_reply"])
            except Exception as tattoo_soft_e:
                print(f"⚠️ Tattoo soft recover (missing body parts) failed: {tattoo_soft_e}")
            if not ns.tattoo_soft_recover:
                ns.api_failure_reason = "booking_claimed_without_create_appointment_tool"

    # «تم تعديل كل المواعيد» etc. without enough successful update_appointment_date calls (bulk user request).
    if not ns.api_failure_reason and _bot_reply_claims_bulk_all_appointments_updated(
        ns.parsed_response.get("bot_reply") or ""
    ):
        ns.nrow = 0
        if ns.customer_phone_clean:
            try:
                ns.nrow = await _count_live_reschedule_row_total(ns.customer_phone_clean)
            except Exception as bulk_cnt_e:
                print(f"WARNING: bulk update row count failed: {bulk_cnt_e}")
        if ns.update_appointment_date_success_count == 0:
            ns.api_failure_reason = "bulk_update_claimed_without_successful_update_appointment_date"
        elif ns.nrow >= 2 and ns.update_appointment_date_success_count < ns.nrow:
            ns.api_failure_reason = (
                f"bulk_update_incomplete:crm_rows~{ns.nrow}_but_only_"
                f"{ns.update_appointment_date_success_count}_successful_updates"
            )

    # Token usage: when tool calls exist, sum BOTH first and second API call usage (second_response alone misses first call's output)
    ns.first_usage = getattr(ns.response, "usage", None) if ns.tool_calls else None
    ns.usage = getattr(ns.second_response, "usage", None) if ns.tool_calls else getattr(ns.response, "usage", None)
    ns.token_breakdown: dict[str, Any] | None = None
    if ns.tool_calls and ns.first_usage and ns.usage:
        ns.pt1 = getattr(ns.first_usage, "prompt_tokens", 0) or 0
        ns.ct1 = getattr(ns.first_usage, "completion_tokens", 0) or 0
        ns.pt2 = getattr(ns.usage, "prompt_tokens", 0) or 0
        ns.ct2 = getattr(ns.usage, "completion_tokens", 0) or 0
        ns.prompt_tokens_val = ns.pt1 + ns.pt2
        ns.completion_tokens_val = ns.ct1 + ns.ct2
        ns.cost1 = _compute_cost_from_usage(ns.selected_model, ns.pt1, ns.ct1)
        ns.cost2 = _compute_cost_from_usage(ns.final_response_model_used, ns.pt2, ns.ct2)
        ns.tokens_val = ns.prompt_tokens_val + ns.completion_tokens_val
        ns.cost_info = {
            "input_cost_usd": round(
                (ns.cost1.get("input_cost_usd", 0) or 0) + (ns.cost2.get("input_cost_usd", 0) or 0), 6
            ),
            "output_cost_usd": round(
                (ns.cost1.get("output_cost_usd", 0) or 0) + (ns.cost2.get("output_cost_usd", 0) or 0), 6
            ),
            "cost_usd": round((ns.cost1.get("cost_usd", 0) or 0) + (ns.cost2.get("cost_usd", 0) or 0), 6),
        }
        ns.token_breakdown = {
            "first_gpt_call": {
                "model": ns.selected_model,
                "prompt_tokens": ns.pt1,
                "completion_tokens": ns.ct1,
                "total_tokens": ns.pt1 + ns.ct1,
                **ns.cost1,
            },
            "second_gpt_call": {
                "model": ns.final_response_model_used,
                "prompt_tokens": ns.pt2,
                "completion_tokens": ns.ct2,
                "total_tokens": ns.pt2 + ns.ct2,
                **ns.cost2,
            },
        }
    else:
        ns.tokens_val = (
            (
                ns.usage.total_tokens
                or (getattr(ns.usage, "prompt_tokens", 0) or 0) + (getattr(ns.usage, "completion_tokens", 0) or 0)
            )
            if ns.usage
            else None
        )
        ns.prompt_tokens_val = getattr(ns.usage, "prompt_tokens", None) if ns.usage else None
        ns.completion_tokens_val = getattr(ns.usage, "completion_tokens", None) if ns.usage else None
        ns.cost_info = (
            _compute_cost_from_usage(ns.final_response_model_used, ns.prompt_tokens_val or 0, ns.completion_tokens_val or 0)
            if (ns.prompt_tokens_val is not None or ns.completion_tokens_val is not None)
            else {}
        )
        if ns.usage and ns.prompt_tokens_val is not None:
            ns.token_breakdown = {
                "single_call": {
                    "model": ns.final_response_model_used,
                    "prompt_tokens": ns.prompt_tokens_val,
                    "completion_tokens": ns.completion_tokens_val or 0,
                    "total_tokens": ns.tokens_val,
                    **ns.cost_info,
                }
            }
    ns.flow_meta = {
        "model": ns.selected_model,
        "orchestration_model": ns.selected_model,
        "final_response_model": ns.final_response_model_used,
        "stage_models": {
            "planning": ns.selected_model,
            "final_response": ns.final_response_model_used,
        },
        "ai_raw_response": ns.gpt_raw_content[:2000] if ns.gpt_raw_content else None,
        "ai_query_summary": ns.flow_ai_query_summary,
        "bot_sent_to_ai": ns.flow_bot_sent_to_ai_full,
        "customer_context_sent": ns.flow_customer_context_sent,
        "tool_calls": ns.tool_names if ns.tool_names else None,
        "tokens": ns.tokens_val,
        "prompt_tokens": ns.prompt_tokens_val,
        "completion_tokens": ns.completion_tokens_val,
        "token_breakdown": ns.token_breakdown,
        **ns.cost_info,
    }
    if ns.api_failure_reason:
        ns.flow_meta["error"] = ns.api_failure_reason
    if ns.tool_calls and ns.tool_round_trips:
        ns.flow_meta["ai_first_response"] = (
            ns.ai_first_response_with_tools[:1500] if ns.ai_first_response_with_tools else None
        )
        ns.flow_meta["tool_round_trips"] = ns.tool_round_trips
    ns._submit_fail = _extract_submit_booking_failure_details(ns.tool_round_trips)
    if ns._submit_fail:
        ns.st = config.user_booking_state[ns.user_id]
        ns.retry_meta = dict(ns.st.get("booking_retry_meta") or {})
        ns.fail_count = int(ns.retry_meta.get("failed_submit_count") or 0) + 1
        ns.last_activity = (
            (ns._submit_fail.get("activity_trace") or {})
            if isinstance(ns._submit_fail.get("activity_trace"), dict)
            else {}
        )
        ns.retry_meta = {
            "failed_submit_count": ns.fail_count,
            "last_error_code": ns._submit_fail.get("error_type") or ns.api_failure_reason or "validation_error",
            "last_error_message": ns._submit_fail.get("human_readable_reason"),
            "last_missing_fields": list(ns._submit_fail.get("missing_fields") or []),
            "last_invalid_fields": dict(ns._submit_fail.get("invalid_fields") or {}),
            "last_conflicting_fields": dict(ns._submit_fail.get("conflicting_fields") or {}),
            "last_payload_sent": ns._submit_fail.get("tool_args"),
            "last_activity_trace": ns.last_activity,
            "last_failure_stage": ns.last_activity.get("failure_stage"),
            "last_pipeline_phase": ns.last_activity.get("pipeline_phase"),
        }
        ns.st["booking_retry_meta"] = ns.retry_meta
        print(
            "[BOOKING_RETRY] "
            + json.dumps(
                {
                    "user_id": ns.user_id,
                    "failed_submit_count": ns.fail_count,
                    "last_error_code": ns.retry_meta["last_error_code"],
                    "last_failure_stage": ns.retry_meta["last_failure_stage"],
                    "last_pipeline_phase": ns.retry_meta["last_pipeline_phase"],
                    "last_missing_fields": ns.retry_meta["last_missing_fields"],
                    "last_invalid_fields": ns.retry_meta["last_invalid_fields"],
                    "last_conflicting_fields": ns.retry_meta["last_conflicting_fields"],
                },
                ensure_ascii=False,
                default=str,
            )[:12000]
        )
        ns.flow_meta["booking_retry"] = ns.retry_meta
    elif "booking_retry_meta" in config.user_booking_state.get(ns.user_id, {}):
        # Clear retry state on non-failure turns to avoid stale handover triggers.
        if not ns.api_failure_reason:
            config.user_booking_state[ns.user_id].pop("booking_retry_meta", None)
    ns.parsed_response["_flow_meta"] = ns.flow_meta

    if ns.cost_info:
        print(
            f"💰 GPT usage: input={ns.prompt_tokens_val} tokens (${ns.cost_info.get('input_cost_usd', 0):.6f}) | output={ns.completion_tokens_val} tokens (${ns.cost_info.get('output_cost_usd', 0):.6f}) | total=${ns.cost_info.get('cost_usd', 0):.6f}"
        )

    # ============================================================
    # PRICING: Use selector files only (no system API)
    # Prices come from ADDITIONAL RELEVANT CONTEXT (selector-retrieved files).
    # ============================================================
    ns._USE_SYSTEM_API_FOR_PRICING = False  # Set True to revert to get_pricing_details API
    if ns._USE_SYSTEM_API_FOR_PRICING and ns.is_price_question:
        ns.booking_state = config.user_booking_state[ns.user_id]
        ns.pricing_payload_to_send = ns.latest_pricing_payload
        ns.service_id_for_sync = _safe_int(ns.booking_state.get("service_id"))
        if ns.service_id_for_sync is None and getattr(config, "BOOKING_LEGACY_INFERENCE", False):
            ns.inferred_service = _infer_service_id_for_pricing(ns.user_input, ns.current_gender, ns.booking_state)
            if ns.inferred_service is not None:
                ns.booking_state["service_id"] = ns.inferred_service
                ns.service_id_for_sync = ns.inferred_service

        if ns.pricing_payload_to_send is None:
            ns.selected_body_parts = _normalize_body_part_ids(ns.booking_state.get("body_part_ids"))

            if ns.service_id_for_sync is None:
                ns.parsed_response["action"] = "ask_for_details_for_booking"
                ns.parsed_response["bot_reply"] = _pricing_missing_details_reply(ns.current_preferred_lang, "service")
            elif ns.service_id_for_sync in ns.body_part_required_service_ids and not ns.selected_body_parts:
                ns.parsed_response["action"] = "ask_for_details_for_booking"
                ns.parsed_response["bot_reply"] = _pricing_missing_details_reply(ns.current_preferred_lang, "body_part")
            else:
                ns.pricing_call_args: dict[str, Any] = {"service_id": ns.service_id_for_sync}
                ns.machine_id_for_sync = _safe_int(ns.booking_state.get("machine_id"))
                ns.branch_id_for_sync = _safe_int(ns.booking_state.get("branch_id"))
                if ns.machine_id_for_sync is not None:
                    ns.pricing_call_args["machine_id"] = ns.machine_id_for_sync
                if ns.selected_body_parts:
                    ns.pricing_call_args["body_part_ids"] = ns.selected_body_parts
                if ns.branch_id_for_sync is not None:
                    ns.pricing_call_args["branch_id"] = ns.branch_id_for_sync

                try:
                    ns.pricing_result = await api_integrations.get_pricing_details(**ns.pricing_call_args)
                    if isinstance(ns.pricing_result, dict) and ns.pricing_result.get("success"):
                        ns.pricing_payload_to_send = ns.pricing_result.get("data")
                        ns.booking_state["last_pricing_payload"] = ns.pricing_payload_to_send
                        _remember_booking_selection(ns.user_id, ns.pricing_call_args)
                    else:
                        ns.parsed_response["action"] = "ask_for_details_for_booking"
                        ns.parsed_response["bot_reply"] = _pricing_missing_details_reply(
                            ns.current_preferred_lang, "unavailable"
                        )
                except Exception as pricing_sync_error:
                    print(f"⚠️ Pricing sync fetch failed: {pricing_sync_error}")
                    ns.parsed_response["action"] = "ask_for_details_for_booking"
                    ns.parsed_response["bot_reply"] = _pricing_missing_details_reply(
                        ns.current_preferred_lang, "unavailable"
                    )

        if ns.pricing_payload_to_send is not None:
            ns.parsed_response["action"] = "answer_question"
            ns.parsed_response["bot_reply"] = _build_exact_pricing_reply(
                ns.current_preferred_lang,
                ns.pricing_payload_to_send,
            )

    # AI-PRIMARY: Bot sends AI reply as-is. No language validation/rewrite.
    return ns.parsed_response
