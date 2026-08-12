"""Core _process_and_respond phase 7."""

from __future__ import annotations

import asyncio
import datetime
import re
from typing import Any, cast

import config

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase7(ctx: dict) -> Any:
    _build_firestore_user_candidates = cast(Any, ctx.get("_build_firestore_user_candidates"))
    _is_plausible_extracted_customer_name = cast(Any, ctx.get("_is_plausible_extracted_customer_name"))
    action = cast(Any, ctx.get("action"))
    alt_candidate = cast(Any, ctx.get("alt_candidate"))
    bot_reply_text = cast(Any, ctx.get("bot_reply_text"))
    candidate = cast(Any, ctx.get("candidate"))
    candidate_ref = cast(Any, ctx.get("candidate_ref"))
    candidate_snap = cast(Any, ctx.get("candidate_snap"))
    candidate_user_id = cast(Any, ctx.get("candidate_user_id"))
    candidate_user_ids = cast(Any, ctx.get("candidate_user_ids"))
    canonical_user_id = cast(Any, ctx.get("canonical_user_id"))
    conversation_id = cast(Any, ctx.get("conversation_id"))
    current_conversation_id = cast(Any, ctx.get("current_conversation_id"))
    current_gender = cast(Any, ctx.get("current_gender"))
    current_preferred_lang = cast(Any, ctx.get("current_preferred_lang"))
    db = cast(Any, ctx.get("db"))
    detected_gender_from_gpt = cast(Any, ctx.get("detected_gender_from_gpt"))
    detected_language = cast(Any, ctx.get("detected_language"))
    detected_name_from_gpt = cast(Any, ctx.get("detected_name_from_gpt"))
    e = cast(Any, ctx.get("e"))
    escalation_reason = cast(Any, ctx.get("escalation_reason"))
    get_canonical_user_id_and_phone = cast(Any, ctx.get("get_canonical_user_id_and_phone"))
    get_firestore_db = cast(Any, ctx.get("get_firestore_db"))
    idx_err = cast(Any, ctx.get("idx_err"))
    is_social_channel = cast(Any, ctx.get("is_social_channel"))
    log_report_event = cast(Any, ctx.get("log_report_event"))
    notify_error = cast(Any, ctx.get("notify_error"))
    notify_human_on_whatsapp = cast(Any, ctx.get("notify_human_on_whatsapp"))
    raw_user_id = cast(Any, ctx.get("raw_user_id"))
    route_social_contact_request = cast(Any, ctx.get("route_social_contact_request"))
    social_route = cast(Any, ctx.get("social_route"))
    trigger_source = cast(Any, ctx.get("trigger_source"))
    user_data = cast(Any, ctx.get("user_data"))
    user_doc_ref = cast(Any, ctx.get("user_doc_ref"))
    user_id = cast(Any, ctx.get("user_id"))
    user_input_to_process = cast(Any, ctx.get("user_input_to_process"))
    user_name = cast(Any, ctx.get("user_name"))
    user_persistence = cast(Any, ctx.get("user_persistence"))
    users_coll = cast(Any, ctx.get("users_coll"))
    if is_social_channel(user_data.get("channel")):
        social_force_intent = None
        if action in {
            "human_handover",
            "human_handover_confirmed",
            "human_handover_initial_ask",
        }:
            social_force_intent = "human"
        elif action in {
            "confirm_booking_details",
            "ask_for_details_for_booking",
            "confirm_appointment_reschedule",
            "ask_for_service_type",
            "ask_for_tattoo_photo",
        }:
            social_force_intent = "booking"
        if social_force_intent:
            social_route = route_social_contact_request(
                user_input_to_process,
                user_data,
                current_preferred_lang,
                force_intent=social_force_intent,
            )
            if social_route:
                action = "answer_question"
                bot_reply_text = social_route.reply
                handover_degree = "none"
                escalation_reason_from_gpt = None
                user_data["awaiting_human_handover_confirmation"] = False
            else:
                # GPT/router booking/handover without explicit user handoff intent must
                # stay on the canonical AI answer path — never open branch/gender collection.
                print(
                    "[_process_and_respond] social: declining force_intent="
                    f"{social_force_intent} without explicit handoff → answer_question"
                )
                action = "answer_question"
                handover_degree = "none"
                escalation_reason_from_gpt = None
                user_data["awaiting_human_handover_confirmation"] = False
                # Drop booking/branch/WhatsApp handoff wording that leaked from GPT tools.
                _leak = re.compile(
                    r"(?:أي\s*فرع|which\s*branch|whatsapp|واتساب|antelias|أنطلياس|"
                    r"ramlet|الرملة|are\s*you\s*male\s*or\s*female|"
                    r"شاب\s*أو\s*صبية|book(?:ing)?\s*(?:an?\s*)?appointment)",
                    re.IGNORECASE | re.UNICODE,
                )
                if bot_reply_text and _leak.search(str(bot_reply_text)):
                    bot_reply_text = None
                    user_data["_social_force_fresh_answer"] = True

    def _build_local_firestore_user_candidates(canonical_user_id: str, raw_user_id: str) -> list:
        candidates = []
        for candidate in [canonical_user_id, raw_user_id]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
            if candidate and (candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10)):
                alt_candidate = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
                if alt_candidate not in candidates:
                    candidates.append(alt_candidate)
        return candidates

    async def _resolve_conversation_doc_ref(users_coll: Any, conversation_id: str, canonical_user_id: str) -> Any:
        candidate_user_ids = _build_local_firestore_user_candidates(canonical_user_id, user_id)
        last_ref = None
        last_snap = None
        for candidate_user_id in candidate_user_ids:
            candidate_ref = (
                users_coll.document(candidate_user_id)
                .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                .document(conversation_id)
            )
            candidate_snap = await asyncio.to_thread(candidate_ref.get)
            last_ref = candidate_ref
            last_snap = candidate_snap
            if candidate_snap.exists:
                return candidate_ref, candidate_snap, candidate_user_id
        return last_ref, last_snap, canonical_user_id

    async def _activate_ai_handover(escalation_reason: str, trigger_source: str) -> bool:
        """Switch conversation to waiting_human, notify admins. Returns True if Firestore was updated."""
        from utils.utils import (
            conversation_any_path_post_release_blocked,
            merge_conversation_user_id_variants,
            update_conversation_on_all_existing_paths,
        )

        # Instagram/Facebook must never enter the dashboard human-takeover queue.
        if is_social_channel(user_data.get("channel")):
            print(
                f"[_activate_ai_handover] blocked for social channel "
                f"channel={user_data.get('channel')} trigger={trigger_source}"
            )
            return False

        wrote = False
        db = get_firestore_db()
        if db and current_conversation_id:
            try:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                update_payload = {
                    "status": "waiting_human",
                    "human_takeover_active": True,
                    "human_takeover_requested": True,
                    "operator_id": None,
                    "conversation_state": "waiting_for_operator",
                    "escalation_reason": escalation_reason,
                    "escalation_time": datetime.datetime.now(),
                    "last_updated": datetime.datetime.now(),
                    "post_release_escalation_suppressed_until": None,
                }
                # User explicitly confirmed transfer — allow even during cooldown
                if trigger_source not in ("ai_handover_confirmed",):
                    if await conversation_any_path_post_release_blocked(current_conversation_id, user_id):
                        print(
                            f"⚠️ _activate_ai_handover skipped: post-release cooldown (trigger={trigger_source}) conv={current_conversation_id}"
                        )
                        return False
                n = await update_conversation_on_all_existing_paths(current_conversation_id, user_id, update_payload)
                if n == 0:
                    print(f"⚠️ Conversation {current_conversation_id} not found in Firestore on any user path")
                else:
                    wrote = True
                    print(f"✅ Conversation {current_conversation_id} set to waiting_human (AI decision, {n} path(s))")
                    try:
                        from services.live_chat_service import live_chat_service

                        live_chat_service.invalidate_cache()
                        await live_chat_service._refresh_index_for_conversation(
                            canonical_user_id, current_conversation_id
                        )
                    except Exception as idx_err:
                        print(f"⚠️ Index refresh after AI handover: {idx_err}")
            except Exception as e:
                print(f"⚠️ Failed to update handover state in Firestore: {e}")

        if not wrote:
            return False

        for vid in merge_conversation_user_id_variants("", user_id):
            config.user_in_human_takeover_mode[vid] = True

        notify_human_on_whatsapp(
            user_name, current_gender, user_input_to_process, type_of_notification=f"AI handover - {escalation_reason}"
        )

        try:
            from services.human_takeover_notification_service import human_takeover_notification_service

            await human_takeover_notification_service.notify_and_audit_handoff(
                user_id=user_id,
                user_gender=current_gender,
                customer_name=user_name,
                customer_phone=user_data.get("phone_number", "Unknown"),
                escalation_reason=escalation_reason,
                last_message=user_input_to_process,
                trigger_source=trigger_source,
                conversation_id=current_conversation_id,
                tenant_id=user_data.get("tenant_id") or user_data.get("tenantId"),
                channel=user_data.get("channel"),
                extra_details={"action": action},
            )
        except Exception as notify_error:
            print(f"⚠️ Failed to send AI handoff template/audit: {notify_error}")
        return True

    # Update language from GPT's detection
    if detected_language and detected_language in ["en", "ar", "fr", "franco"]:
        previous_lang = user_data.get("user_preferred_lang", "ar")
        if previous_lang != detected_language:
            user_data["user_preferred_lang"] = detected_language
            user_persistence.save_user_language(user_id, detected_language)
            print(f"[_process_and_respond] 🌐 Language updated by GPT: {previous_lang} → {detected_language}")
        else:
            print(f"[_process_and_respond] 🌐 Language confirmed by GPT: {detected_language}")
        # Update local variable so all follow-up messages in this function use the detected language
        current_preferred_lang = detected_language

    # Save detected_name from AI (AI-primary: AI extracts, bot saves)
    if detected_name_from_gpt and isinstance(detected_name_from_gpt, str):
        name_clean = detected_name_from_gpt.strip()
        name_pattern = r"^[A-Za-z\u00C0-\u00FF\u0600-\u06FF\s\-\']+$"
        if (
            2 <= len(name_clean) <= 50
            and re.match(name_pattern, name_clean, re.UNICODE)
            and _is_plausible_extracted_customer_name(name_clean, user_input_to_process)
        ):
            config.user_names[user_id] = name_clean
            user_data["collected_name"] = name_clean
            user_data["name_source"] = "ai_extracted"
            user_data["awaiting_name_input"] = False
            config.user_greeting_stage[user_id] = 2
            db = get_firestore_db()
            if db:
                try:
                    app_id_for_firestore = "linas-ai-bot-backend"
                    user_doc_ref = (
                        db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
                    )
                    user_doc_ref.update({"name": name_clean, "last_updated": datetime.datetime.now()})
                except Exception as e:
                    print(f"⚠️ Failed to save name to Firestore: {e}")
            log_report_event(
                "name_saved", name_clean, current_gender, {"method": "AI Extraction", "whatsapp_id": user_id}
            )
            print(f"✅ Saved name_len={len(str(name_clean or ''))} from AI for user ...{str(user_id)[-4:]}")
            user_name = name_clean
        elif 2 <= len(name_clean) <= 50 and re.match(name_pattern, name_clean, re.UNICODE):
            print(
                f"⚠️ Rejected AI extracted name (not plausible vs message): "
                f"'{name_clean[:80]}' | message_len={len(user_input_to_process or '')}"
            )

    if detected_gender_from_gpt and config.user_gender.get(user_id) != detected_gender_from_gpt:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "User Input Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(
            user_id, detected_gender_from_gpt, phone=user_id, name=config.user_names.get(user_id, user_name)
        )
    elif (
        detected_gender_from_gpt
        and config.user_gender.get(user_id) == "unknown"
        and detected_gender_from_gpt in ["male", "female"]
    ):
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "GPT Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(
            user_id, detected_gender_from_gpt, phone=user_id, name=config.user_names.get(user_id, user_name)
        )
    _pack = [
        "_",
        "_build_firestore_user_candidates",
        "_is_plausible_extracted_customer_name",
        "_leak",
        "action",
        "alt_candidate",
        "app_id_for_firestore",
        "bot_reply_text",
        "candidate",
        "candidate_ref",
        "candidate_snap",
        "candidate_user_id",
        "candidate_user_ids",
        "candidates",
        "canonical_user_id",
        "conversation_any_path_post_release_blocked",
        "conversation_id",
        "current_conversation_id",
        "current_gender",
        "current_preferred_lang",
        "db",
        "detected_gender_from_gpt",
        "detected_language",
        "detected_name_from_gpt",
        "e",
        "escalation_reason",
        "escalation_reason_from_gpt",
        "get_canonical_user_id_and_phone",
        "get_firestore_db",
        "handover_degree",
        "human_takeover_notification_service",
        "idx_err",
        "is_social_channel",
        "last_ref",
        "last_snap",
        "live_chat_service",
        "log_report_event",
        "merge_conversation_user_id_variants",
        "n",
        "name_clean",
        "name_pattern",
        "notify_error",
        "notify_human_on_whatsapp",
        "previous_lang",
        "raw_user_id",
        "route_social_contact_request",
        "social_force_intent",
        "social_route",
        "trigger_source",
        "update_conversation_on_all_existing_paths",
        "update_payload",
        "user_data",
        "user_doc_ref",
        "user_id",
        "user_input_to_process",
        "user_name",
        "user_persistence",
        "users_coll",
        "vid",
        "wrote",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
