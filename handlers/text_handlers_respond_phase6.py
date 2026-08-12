"""Core _process_and_respond phase 6."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import config
from handlers.text_handlers_respond_intent import (
    _clean_reply_text,
    _flow_meta_has_crm_booking_confirmation,
    _reply_claims_booking_done,
)
from handlers.text_handlers_respond_reply import (
    _reply_offers_handover_confirmation,
    _user_explicitly_requests_human_agent,
)
from handlers.text_handlers_wa_me_handoff import build_wa_me_handoff_guidance

_PHASE_HALT = "_PHASE_HALT"


def _coerce_unauthorized_to_wa_me(
    *,
    user_data: dict,
    current_preferred_lang: str,
    reason: str,
) -> tuple[str, str]:
    """Replace unauthorized human_handover coerce with WhatsApp/wa.me guidance.

    When Requests capture is active, booking/appointment claim paths must not force wa.me.
    """
    booking_reasons = {
        "booking_retry_exceeded",
        "booking_claim_without_crm",
    }
    if reason in booking_reasons or reason.startswith("booking_"):
        try:
            from services.requests.capture import (
                appointment_pending_confirmation_message,
                skip_forced_booking_wa_me,
            )

            tenant_id = str(
                (user_data or {}).get("tenant_id")
                or (user_data or {}).get("tenantId")
                or (user_data or {}).get("workspace_id")
                or ""
            ).strip()
            if skip_forced_booking_wa_me(tenant_id):
                reply = appointment_pending_confirmation_message(current_preferred_lang)
                print(f"[_process_and_respond] requests capture active → skip forced wa.me booking handoff ({reason})")
                return "answer_question", reply
        except Exception as exc:
            print(f"[_process_and_respond] requests capture gate check failed: {exc}")

    reply = build_wa_me_handoff_guidance(user_data=user_data, language=current_preferred_lang)
    print(f"[_process_and_respond] unauthorized handover coerce blocked → wa.me handoff ({reason})")
    return "answer_question", reply


async def text_handlers_respond_phase6(ctx: dict) -> Any:
    canonical_user_id = cast(Any, ctx.get("canonical_user_id"))
    current_conversation_id = cast(Any, ctx.get("current_conversation_id"))
    current_gender = cast(Any, ctx.get("current_gender"))
    current_preferred_lang = cast(Any, ctx.get("current_preferred_lang"))
    db = cast(Any, ctx.get("db"))
    e = cast(Any, ctx.get("e"))
    get_canonical_user_id_and_phone = cast(Any, ctx.get("get_canonical_user_id_and_phone"))
    get_dynamic_message = cast(Any, ctx.get("get_dynamic_message"))
    get_firestore_db = cast(Any, ctx.get("get_firestore_db"))
    gpt_response_data = cast(Any, ctx.get("gpt_response_data"))
    is_post_takeover_escalation_cooldown = cast(Any, ctx.get("is_post_takeover_escalation_cooldown"))
    user_data = cast(Any, ctx.get("user_data"))
    user_id = cast(Any, ctx.get("user_id"))
    user_input_to_process = cast(Any, ctx.get("user_input_to_process"))
    users_coll = cast(Any, ctx.get("users_coll"))
    if not gpt_response_data:
        print("[_process_and_respond] ERROR: gpt_response_data is empty — synthesizing fallback reply")
        gpt_response_data = {
            "action": "answer_question",
            "bot_reply": (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "عذراً، ما قدرت أكمل المعالجة. جرّب مرة ثانية أو تواصل معنا مباشرة."
            ),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender,
            "_flow_meta": {"error": "empty_gpt_response_payload"},
        }

    action = gpt_response_data.get("action")
    bot_reply_text = gpt_response_data.get("bot_reply")
    handover_degree = str(gpt_response_data.get("handover_degree") or "none").strip().lower()
    _flow_error_reason = None  # For Activity Flow: which step failed
    detected_gender_from_gpt = gpt_response_data.get("detected_gender")
    detected_language = gpt_response_data.get("detected_language")
    detected_name_from_gpt = gpt_response_data.get("detected_name")
    escalation_reason_from_gpt = gpt_response_data.get("escalation_reason")
    flow_meta = gpt_response_data.get("_flow_meta") or {}
    booking_retry = flow_meta.get("booking_retry") or {}

    if int(booking_retry.get("failed_submit_count") or 0) >= 5:
        # Product: no unauthorized operator-queue coerce — WhatsApp/wa.me guidance only.
        action, bot_reply_text = _coerce_unauthorized_to_wa_me(
            user_data=user_data,
            current_preferred_lang=current_preferred_lang,
            reason="booking_retry_exceeded",
        )
        escalation_reason_from_gpt = None
        _flow_error_reason = (
            "Step: submit_booking_intent retry guard | exceeded 5 failed booking attempts | "
            f"error_code={booking_retry.get('last_error_code') or 'unknown'} | "
            f"failure_stage={booking_retry.get('last_failure_stage') or 'unknown'} | "
            f"pipeline_phase={booking_retry.get('last_pipeline_phase') or 'unknown'} | "
            "wa_me_handoff=1"
        )
        flow_meta["booking_retry_exceeded"] = True
        print(
            "[_process_and_respond] booking retry guard → wa.me handoff | "
            f"count={booking_retry.get('failed_submit_count')} | "
            f"error_code={booking_retry.get('last_error_code')}"
        )

    # When GPT fails (error in flow_meta): if user in waiting queue → waiting message; else → wa.me (not queue)
    if flow_meta.get("error") and action != "human_handover":
        in_waiting = config.user_in_human_takeover_mode.get(user_id, False)
        if not in_waiting and current_conversation_id:
            try:
                db = get_firestore_db()
                if db:
                    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                    users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
                    for uid in [canonical_user_id, user_id]:
                        if not uid:
                            continue
                        ref = (
                            users_coll.document(uid)
                            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                            .document(current_conversation_id)
                        )
                        snap = await asyncio.to_thread(ref.get)
                        if snap.exists:
                            d = snap.to_dict() or {}
                            if d.get("human_takeover_active") and not d.get("operator_id"):
                                in_waiting = True
                            break
            except Exception as e:
                print(f"[_process_and_respond] ⚠️ Waiting-check on error failed: {e}")
        if in_waiting:
            bot_reply_text = (
                get_dynamic_message("waiting_queue_message", current_preferred_lang)
                or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
            )
            action = "answer_question"
            print(
                f"[_process_and_respond] GPT error but user ...{str(user_id)[-4:]} in waiting queue → sending waiting message"
            )
        else:
            action, bot_reply_text = _coerce_unauthorized_to_wa_me(
                user_data=user_data,
                current_preferred_lang=current_preferred_lang,
                reason=f"flow_meta_error:{flow_meta.get('error')}",
            )
            escalation_reason_from_gpt = None

    _handover_offer_needs_confirmation = (
        bool(bot_reply_text)
        and _reply_offers_handover_confirmation(str(bot_reply_text or ""))
        and not _user_explicitly_requests_human_agent(user_input_to_process)
        and not flow_meta.get("error")
        and not flow_meta.get("booking_retry_exceeded")
        and str(escalation_reason_from_gpt or "").strip().lower() != "technical_error"
    )

    # AI-assessed handover degree: if GPT says medium/high, escalate, but do not
    # skip a permission question that the model already wrote for the user.
    if (
        handover_degree in ("medium", "high")
        and action not in ("human_handover", "human_handover_confirmed", "human_handover_initial_ask")
        and not is_post_takeover_escalation_cooldown(user_data)
    ):
        if _handover_offer_needs_confirmation:
            print(
                f"[_process_and_respond] handover_degree={handover_degree} with permission wording → human_handover_initial_ask"
            )
            action = "human_handover_initial_ask"
        else:
            print(f"[_process_and_respond] 🔄 handover_degree={handover_degree} → overriding action to human_handover")
            action = "human_handover"
        escalation_reason_from_gpt = escalation_reason_from_gpt or "frustration_detected"
    elif handover_degree in ("medium", "high") and is_post_takeover_escalation_cooldown(user_data):
        print(
            f"[_process_and_respond] post-release cooldown: ignoring handover_degree={handover_degree} (keeping action={action})"
        )

    # Defensive normalization: GPT can occasionally return non-schema actions like "none".
    # If we still have a usable bot reply, treat it as a normal answer instead of failing to fallback.
    known_actions = {
        "initial_greet_and_ask_gender",
        "ask_gender",
        "confirm_gender",
        "confirm_booking_details",
        "human_handover_initial_ask",
        "human_handover_confirmed",
        "return_to_normal_chat",
        "human_handover",
        "ask_for_details_for_booking",
        "ask_for_service_type",
        "ask_for_details",
        "ask_for_tattoo_photo",
        "ask_clarification",
        "answer_question",
        "normal_chat",
        "unknown_query",
        "provide_info",
        "tool_call",
        "check_customer_status",
        "confirm_appointment_reschedule",
        "rate_limit_exceeded",
        "content_moderated",
    }
    action = str(action or "").strip().lower()
    action_was_coerced = False
    if action not in known_actions:
        if bot_reply_text:
            print(
                f"[_process_and_respond] ⚠️ Unexpected GPT action '{action}'. "
                "Using 'answer_question' since bot_reply is present."
            )
            action = "answer_question"
            action_was_coerced = True
        else:
            bad_action = action
            action, bot_reply_text = _coerce_unauthorized_to_wa_me(
                user_data=user_data,
                current_preferred_lang=current_preferred_lang,
                reason=f"bad_action:{bad_action}",
            )
            escalation_reason_from_gpt = None
            _flow_error_reason = (
                f"Step: Parse GPT response | Action '{bad_action}' not in known_actions, "
                f"bot_reply empty. flow_meta.error={flow_meta.get('error', 'none')} | wa_me_handoff=1"
            )

    if action == "human_handover" and _handover_offer_needs_confirmation:
        print(
            "[_process_and_respond] GPT requested human_handover but bot_reply asks permission → human_handover_initial_ask"
        )
        action = "human_handover_initial_ask"

    # AI-PRIMARY: No bot-side overrides. Send AI reply as-is.

    # If we had to coerce an invalid action from GPT, keep the full AI wording
    # instead of compressing it into the brief turn-by-turn format.
    if action_was_coerced:
        bot_reply_text = _clean_reply_text(str(bot_reply_text or ""))
    # AI-PRIMARY: No turn-by-turn truncation or greeting strip. Send AI reply as-is.

    # Allow summary + confirmation request before submit; if the model falsely claims that booking
    # already happened or that the request was already sent to the system without CRM success,
    # send wa.me guidance instead of putting the user in the operator queue.
    if not _flow_meta_has_crm_booking_confirmation(flow_meta) and _reply_claims_booking_done(str(bot_reply_text or "")):
        print(
            "[_process_and_respond] BLOCKED booking claim: text claims booking/request already happened "
            "without submit_booking_intent/create_appointment success+booking_flow_state=booked → wa.me"
        )
        action, bot_reply_text = _coerce_unauthorized_to_wa_me(
            user_data=user_data,
            current_preferred_lang=current_preferred_lang,
            reason="booking_claim_without_crm",
        )
        escalation_reason_from_gpt = None
        _flow_error_reason = (
            "Step: Booking execution guard | assistant claimed booking/request already happened "
            "without real CRM success | wa_me_handoff=1"
        )

    # Unauthorized AI human_handover (no explicit user request / not confirmed flow):
    # never put the user in the operator queue — WhatsApp/wa.me guidance only.
    if (
        action == "human_handover"
        and not _user_explicitly_requests_human_agent(user_input_to_process)
        and not flow_meta.get("booking_retry_exceeded")
    ):
        print("[_process_and_respond] unauthorized human_handover without explicit user request → wa.me handoff")
        action, bot_reply_text = _coerce_unauthorized_to_wa_me(
            user_data=user_data,
            current_preferred_lang=current_preferred_lang,
            reason="ai_human_handover_without_user_request",
        )
        escalation_reason_from_gpt = None
    _pack = [
        "_",
        "_clean_reply_text",
        "_flow_error_reason",
        "_flow_meta_has_crm_booking_confirmation",
        "_handover_offer_needs_confirmation",
        "_reply_claims_booking_done",
        "_reply_offers_handover_confirmation",
        "_user_explicitly_requests_human_agent",
        "action",
        "action_was_coerced",
        "bad_action",
        "booking_retry",
        "bot_reply_text",
        "canonical_user_id",
        "current_conversation_id",
        "current_gender",
        "current_preferred_lang",
        "d",
        "db",
        "detected_gender_from_gpt",
        "detected_language",
        "detected_name_from_gpt",
        "e",
        "escalation_reason_from_gpt",
        "flow_meta",
        "get_canonical_user_id_and_phone",
        "get_dynamic_message",
        "get_firestore_db",
        "gpt_response_data",
        "handover_degree",
        "in_waiting",
        "is_post_takeover_escalation_cooldown",
        "known_actions",
        "ref",
        "snap",
        "uid",
        "user_data",
        "user_id",
        "user_input_to_process",
        "users_coll",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
