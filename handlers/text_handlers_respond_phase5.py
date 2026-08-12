"""Core _process_and_respond phase 5."""
from __future__ import annotations

import config
from services.analytics_events import analytics

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase5(ctx: dict):
    _apply_turn_by_turn_policy = ctx.get('_apply_turn_by_turn_policy')
    _build_arabic_respectful_address = ctx.get('_build_arabic_respectful_address')
    _faq_exc = ctx.get('_faq_exc')
    _is_price_intent = ctx.get('_is_price_intent')
    _ra = ctx.get('_ra')
    _resume_original_question = ctx.get('_resume_original_question')
    ai_primary_mode = ctx.get('ai_primary_mode')
    canonical_user_id = ctx.get('canonical_user_id')
    conv_state = ctx.get('conv_state')
    conversation_history = ctx.get('conversation_history')
    current_conversation_id = ctx.get('current_conversation_id')
    current_gender = ctx.get('current_gender')
    current_preferred_lang = ctx.get('current_preferred_lang')
    detect_reschedule_intent = ctx.get('detect_reschedule_intent')
    firestore_conversation_id = ctx.get('firestore_conversation_id')
    get_bot_chat_response = ctx.get('get_bot_chat_response')
    get_canonical_user_id_and_phone = ctx.get('get_canonical_user_id_and_phone')
    get_conversation_context_for_gpt = ctx.get('get_conversation_context_for_gpt')
    get_conversation_last_ai_response_at = ctx.get('get_conversation_last_ai_response_at')
    get_dynamic_message = ctx.get('get_dynamic_message')
    get_last_bot_message_for_gpt_context = ctx.get('get_last_bot_message_for_gpt_context')
    gpt_response_data = ctx.get('gpt_response_data')
    initial_user_query_to_process_original = ctx.get('initial_user_query_to_process_original')
    is_initial_message_for_gpt = ctx.get('is_initial_message_for_gpt')
    is_post_takeover_escalation_cooldown = ctx.get('is_post_takeover_escalation_cooldown')
    last_ai_response_at = ctx.get('last_ai_response_at')
    local_qa_service = ctx.get('local_qa_service')
    log_interaction = ctx.get('log_interaction')
    query_pre_set_from_booking_confirmation = ctx.get('query_pre_set_from_booking_confirmation')
    query_to_send_to_gpt = ctx.get('query_to_send_to_gpt')
    respectful_address = ctx.get('respectful_address')
    response_language = ctx.get('response_language')
    save_conversation_message_to_firestore = ctx.get('save_conversation_message_to_firestore')
    save_for_training_conversation_log = ctx.get('save_for_training_conversation_log')
    send_message_func = ctx.get('send_message_func')
    update_dashboard_metric_in_firestore = ctx.get('update_dashboard_metric_in_firestore')
    user_data = ctx.get('user_data')
    user_id = ctx.get('user_id')
    user_image_base64 = ctx.get('user_image_base64')
    user_image_format = ctx.get('user_image_format')
    user_input_to_process = ctx.get('user_input_to_process')
    user_name = ctx.get('user_name')
    if not gpt_response_data:
        # Only use raw input when not resuming; do NOT overwrite query pre-set from booking confirmation
        if not _resume_original_question and not query_pre_set_from_booking_confirmation:
            query_to_send_to_gpt = user_input_to_process

        # Restore and combine original question when user replies to clarification (legacy path)
        pending_clarification = user_data.get("pending_clarification_query")
        if pending_clarification:
            query_to_send_to_gpt = f"{pending_clarification}\n[User clarified: {user_input_to_process}]"
            user_data["pending_clarification_query"] = None
            user_data["awaiting_clarification"] = False
            print(
                f"[_process_and_respond] ✅ Restored original query + clarification: '{query_to_send_to_gpt[:80]}...'"
            )

        # DEBUG: Gender confirmation and original query retrieval
        print("[_process_and_respond] 🔍 Gender Check:")
        print(f"  - current_gender: {current_gender}")
        print(f"  - greeting_stage: {config.user_greeting_stage[user_id]}")
        print(
            f"  - initial_query_len={len(str(initial_user_query_to_process_original or ''))}"
        )

        if (
            (not ai_primary_mode)
            and current_gender in ["male", "female"]
            and config.user_greeting_stage[user_id] == 1
            and initial_user_query_to_process_original
        ):
            print(
                f"[_process_and_respond] ✅ Gender confirmed! Answering original query_len={len(str(initial_user_query_to_process_original or ''))}"
            )
            user_data["initial_user_query_to_process"] = None
            query_to_send_to_gpt = initial_user_query_to_process_original
            config.user_greeting_stage[user_id] = 2
            is_initial_message_for_gpt = False

            respectful_address = _build_arabic_respectful_address(current_gender, user_name)
            gender_acknowledgement = "أهلاً بكِ " if current_gender == "female" else "أهلاً بك "
            gender_ack_message = (
                f"{gender_acknowledgement}{respectful_address}! شكراً لتحديد جنسك. سأجيب على استفسارك الأصلي."
            )
            await send_message_func(user_id, gender_ack_message)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                gender_ack_message,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={"handled_by": "ai"},
            )

        # Check Smart Answers / FAQ before GPT. Prefer tenant-safe multi-signal match
        # (not blind 90% similarity). Falls back to legacy matcher only when no tenant.
        print(
            f"[_process_and_respond] 🔍 Checking Q&A DATABASE for query_len={len(str(query_to_send_to_gpt or ''))}"
        )

        is_reschedule_intent = detect_reschedule_intent(query_to_send_to_gpt)
        is_price_intent = _is_price_intent(query_to_send_to_gpt)
        match_result = None
        _faq_tenant = str(user_data.get("tenant_id") or user_data.get("tenantId") or "").strip().lower()
        if _faq_tenant:
            try:
                from services.faq_safe_match import find_safe_faq_match

                match_result = find_safe_faq_match(
                    tenant_id=_faq_tenant,
                    question=query_to_send_to_gpt,
                    language=current_preferred_lang,
                )
            except Exception as _faq_exc:
                print(f"[_process_and_respond] safe FAQ match skipped: {type(_faq_exc).__name__}")
                match_result = None
        else:
            match_result = await local_qa_service.find_match_with_tier(
                query_to_send_to_gpt,
                current_preferred_lang,
            )

        if match_result:
            # 90%+ match: Return Q&A directly
            match_score = match_result.get("match_score", 0)
            match_tier = match_result.get("tier", "direct")
            qa_pair = match_result.get("qa_pair", {})
            qa_response = qa_pair.get("answer", "")
            qa_response = _apply_turn_by_turn_policy(
                "answer_question",
                qa_response,
                current_preferred_lang,
            )
            if not (qa_response or "").strip():
                qa_response = (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، إجابة قاعدة الأسئلة كانت فارغة. جرّب إعادة صياغة السؤال."
                )
                print("[_process_and_respond] WARN: Q&A match had empty answer after policy → generic fallback")

            print("[_process_and_respond] ✅ Q&A MATCH FOUND!")
            if match_tier == "exact":
                print(f"[_process_and_respond] 📊 Match Score: {match_score:.0%} (exact match)")
            elif match_tier == "safe_semantic":
                print(
                    f"[_process_and_respond] 📊 Safe semantic score: {match_result.get('safe_score', match_score):.0%}"
                )
            else:
                print(f"[_process_and_respond] 📊 Match Score: {match_score:.0%} (≥90% threshold)")
            print("[_process_and_respond] 🎯 Returning Q&A directly")
            print("[_process_and_respond] 💰 AI CREDITS SAVED: $0.02-0.05 (NO GPT-4 CALL)")
            print("[_process_and_respond] ⚡ Response Time: ~100-200ms (vs 2-5s with GPT-4)")
            print(f"[_process_and_respond] 🎯 Answer_len={len(str(qa_response or ''))}")
            if _faq_tenant:
                try:
                    from services.faq_metrics import faq_metrics_store

                    faq_metrics_store.record_lookup(tenant_id=_faq_tenant, hit=True, generation_avoided=True)
                except Exception:
                    pass

            await send_message_func(user_id, qa_response)
            qa_pair = match_result.get("qa_pair", {})
            stored_language = match_result.get("matched_language", qa_pair.get("language", "ar"))
            faq_id = qa_pair.get("id")
            if isinstance(faq_id, str) and faq_id.isdigit():
                faq_id = int(faq_id)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                qa_response,
                current_conversation_id,
                user_name,
                user_data.get("phone_number"),
                metadata={
                    "source": "qa_database",
                    "handled_by": "bot",
                    "match_score": match_score,
                    "ai_cost_saved": True,
                    "response_type": "instant",
                    "reply_source": "managed_faq",
                    "faq_match": {
                        "faq_id": faq_id,
                        "stored_question": qa_pair.get("question", ""),
                        "stored_language": stored_language,
                        "user_question": query_to_send_to_gpt,
                        "user_language": current_preferred_lang,
                        "similarity": match_score,
                        "tier": match_result.get("tier", "direct"),
                    },
                },
            )
            await update_dashboard_metric_in_firestore(user_id, "qa_responses_used", 1)
            config.user_greeting_stage[user_id] = 2
            save_for_training_conversation_log(query_to_send_to_gpt, qa_response)
            flow_match_title = "Q&A Match (Exact)" if match_tier == "exact" else "Q&A Match (≥90%)"
            qa_steps = [
                {"step": 1, "title": "User → Bot", "content": query_to_send_to_gpt},
                {
                    "step": 2,
                    "title": flow_match_title,
                    "content": f"Bot matched from Q&A database. Score: {match_score:.0%}. No AI call.",
                },
                {"step": 3, "title": "Bot → User", "content": qa_response, "event_type": "response_sent"},
            ]
            voice_meta = user_data.pop("_voice_flow_meta", None)
            if voice_meta:
                qa_steps = [
                    {
                        "step": 1,
                        "title": "Voice received",
                        "content": "User sent voice message.",
                        "event_type": "voice_received",
                        "status": "success",
                        "message_type": "voice",
                    },
                    {
                        "step": 2,
                        "title": "Transcription completed",
                        "content": f"Result: {voice_meta.get('transcription_length', 0)} chars. Model: {voice_meta.get('transcription_model', 'gpt-4o-transcribe')}.",
                        "event_type": "transcription_completed",
                        "status": "success",
                        "duration_ms": voice_meta.get("transcription_duration_ms"),
                    },
                    {"step": 3, "title": "User → Bot", "content": query_to_send_to_gpt},
                    {
                        "step": 4,
                        "title": flow_match_title,
                        "content": f"Bot matched from Q&A database. Score: {match_score:.0%}. No AI call.",
                    },
                    {"step": 5, "title": "Bot → User", "content": qa_response, "event_type": "response_sent"},
                ]
            log_interaction(
                user_id,
                query_to_send_to_gpt,
                qa_response,
                "qa_database",
                user_name=user_name,
                user_phone=user_data.get("phone_number"),
                user_gender=current_gender,
                customer_exists=user_data.get("crm_customer_exists"),
                customer_file_status=user_data.get("customer_file_status"),
                qa_match_score=match_score,
                flow_steps=qa_steps,
                message_type="voice" if voice_meta else "text",
                user_data=user_data,
                conversation_id=current_conversation_id,
                handler_path="managed_faq",
                outcome=f"faq_{match_tier or 'match'}",
                ai_called=False,
                cost_status="none",
                faq_match={
                    "faq_id": faq_id,
                    "tier": match_result.get("tier", match_tier or "direct"),
                    "similarity": match_score,
                    "stored_language": stored_language,
                },
                pipeline_decisions=[
                    {
                        "step": "faq_match",
                        "decision": match_tier or "match",
                        "similarity": match_score,
                        "faq_id": faq_id,
                    }
                ],
            )
            return _PHASE_HALT
        else:
            if ai_primary_mode:
                print("[_process_and_respond] 🧠 AI-primary mode ON. No FAQ match >=90%, continuing AI-normal flow.")
            if is_reschedule_intent:
                print(
                    "[_process_and_respond] 🔁 Reschedule intent detected. No FAQ match >=90%, continuing booking flow."
                )
            if is_price_intent:
                print(
                    "[_process_and_respond] 💰 Price intent detected. "
                    "No FAQ match >=90%, continuing exact pricing flow."
                )
            # <90% match: GPT + knowledge + style + top 3 relevant Q&A pairs
            print("[_process_and_respond] ℹ️ No Q&A match found (below 90%). Proceeding with GPT-4...")
            print("[_process_and_respond] 💡 GPT will receive top 3 relevant Q&A pairs in context")

            # Fetch conversation history once (same 12h window as normal context) – use for selector and for GPT.
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            conversation_history = await get_conversation_context_for_gpt(
                user_id,
                firestore_conversation_id,
                window_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
                alternate_user_id=canonical_user_id,
            )
            last_ai_response_at = (
                await get_conversation_last_ai_response_at(user_id, current_conversation_id, canonical_user_id)
                if current_conversation_id
                else None
            )
            last_bot_msg = await get_last_bot_message_for_gpt_context(
                user_id,
                current_conversation_id,
                canonical_user_id,
                within_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
            )

            if last_bot_msg and query_to_send_to_gpt:
                try:
                    _meta = last_bot_msg.get("metadata") or {}
                    if _meta.get("source") == "smart_message" and _meta.get("type") == "reminder_24h":
                        from utils.reminder_analytics import classify_reminder_reply_intent

                        _rint = classify_reminder_reply_intent(query_to_send_to_gpt)
                        if _rint:
                            _pn = user_data.get("phone_number")
                            analytics.log_smart_reminder_reply(
                                user_id=user_id,
                                intent=_rint,
                                source_message_id=_meta.get("message_id"),
                                appointment_id=_meta.get("appointment_id"),
                                phone=str(_pn).strip() if _pn else None,
                            )
                except Exception as _ra:
                    print(f"[_process_and_respond] reminder reply analytics: {_ra}")

            # ALWAYS run selector: pass query + context_messages so selector understands what the conversation is about (e.g. user "eh" / "beirut" after we asked branch).
            from services.dynamic_retrieval_service import (
                is_dynamic_retrieval_available,
                retrieve_and_merge,
            )

            custom_context = None
            _dynamic_retrieval_flow_meta = None
            selector_query = query_to_send_to_gpt
            if user_image_base64:
                selector_query = (
                    "The user sent an image (attached below). Examine the image and the conversation context. "
                    "Select which files to load. Do not assume – pick based on what you observe."
                )
            if is_dynamic_retrieval_available():
                merged, _clar, _act, _dynamic_retrieval_flow_meta = await retrieve_and_merge(
                    selector_query,
                    include_price_hint=is_price_intent,
                    response_lang=current_preferred_lang,
                    context_messages=conversation_history,
                    user_image_base64=user_image_base64,
                    user_image_format=user_image_format,
                )
                custom_context = merged if merged else None
                print(f"[_process_and_respond] ✅ Selector ran: action={_act}, context_len={len(custom_context or '')}")
                if custom_context:
                    from services.ai_limits_enforcement import enforce_context_line_budget

                    custom_context, ctx_decision = enforce_context_line_budget(
                        user_id=user_id,
                        user_data=user_data,
                        text=custom_context,
                        consume=True,
                    )
                    if not custom_context and not ctx_decision.allowed:
                        custom_context = None
                        print(
                            f"[_process_and_respond] context_lines_blocked reason={ctx_decision.reason}",
                            flush=True,
                        )

            # Phase 3: Build operational context when resuming (Plan §10)
            operational_context = None
            if user_data.pop("just_returned_from_human_takeover", False):
                takeover_ctx = (
                    "**USER JUST RETURNED FROM HUMAN TAKEOVER (CRITICAL):**\n"
                    "- A human operator just finished with this user. The conversation was released back to the bot.\n"
                    "- **Conversation history sent to you may omit messages from before the release** (technical reset for a clean AI session).\n"
                    "- Do NOT re-escalate to human based on OLD frustration or complaints that are no longer in the history.\n"
                    "- Only hand over if the user EXPLICITLY asks for a human in THIS current message.\n"
                    "- Treat this as a fresh start. Answer their current question normally."
                )
                operational_context = (
                    (operational_context + "\n\n" + takeover_ctx) if operational_context else takeover_ctx
                )
            if _resume_original_question:
                orig_q = user_data.get("original_question") or conv_state.get("original_question")
                ctx = (
                    f"Conversation State:\n"
                    f"- gender: {current_gender}\n"
                    f"- awaiting_gender: false\n"
                    f"- awaiting_clarification: false\n"
                    f'- original_question: "{orig_q or ""}"\n'
                    f'- selected_service: "{user_data.get("selected_service", "")}"\n'
                    f'- last_bot_question_type: "{conv_state.get("last_bot_question_type", "")}"\n\n'
                    f'Current User Message: "{user_input_to_process}"\n\n'
                    f"Task: The user previously asked a question. The bot asked for clarification or gender. "
                    f"The user has now answered. Answer the ORIGINAL question. Do not ask for clarification again."
                )
                operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx
            # When last message was from us (e.g. smart message, notification): give GPT context so it doesn't lose domain
            if last_bot_msg and last_bot_msg.get("text"):
                last_text = (last_bot_msg.get("text") or "")[:500]
                is_smart = (last_bot_msg.get("metadata") or {}).get("source") == "smart_message"
                ctx = f'Last message we sent to the user: "{last_text}"\nDomain: clinic (ليناز ليزر). '
                if is_smart:
                    ctx += "This was a clinic notification. The user might be replying to or asking about it. "
                ctx += "Do not lose context – the user might be talking or asking about this."
                operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx

            if is_post_takeover_escalation_cooldown(user_data):
                cooldown_ctx = (
                    "**POST-RELEASE COOLDOWN (CRITICAL):** This user was recently returned to the bot from human support.\n"
                    "- Do NOT set handover_degree to medium or high based on old messages or past frustration.\n"
                    "- Do NOT choose action human_handover unless they clearly ask to speak to a person **in this message**.\n"
                    "- Answer their current message normally; ignore stale anger/complaints in history for escalation."
                )
                operational_context = (
                    (operational_context + "\n\n" + cooldown_ctx) if operational_context else cooldown_ctx
                )

            gpt_response_data = await get_bot_chat_response(
                user_id=user_id,
                user_input=query_to_send_to_gpt,
                current_context_messages=conversation_history,
                current_gender=current_gender,
                current_preferred_lang=current_preferred_lang,
                response_language=response_language,
                is_initial_message_after_start=is_initial_message_for_gpt,
                initial_user_query_to_process=None,
                custom_knowledge_context=custom_context,
                operational_context=operational_context,
                last_ai_response_at=last_ai_response_at,
                user_image_base64=user_image_base64,
                user_image_format=user_image_format,
            )
    _pack = ['_', '_act', '_apply_turn_by_turn_policy', '_build_arabic_respectful_address', '_clar', '_dynamic_retrieval_flow_meta', '_faq_exc', '_faq_tenant', '_is_price_intent', '_meta', '_pn', '_ra', '_resume_original_question', '_rint', 'ai_primary_mode', 'canonical_user_id', 'classify_reminder_reply_intent', 'conv_state', 'conversation_history', 'cooldown_ctx', 'ctx', 'ctx_decision', 'current_conversation_id', 'current_gender', 'current_preferred_lang', 'custom_context', 'detect_reschedule_intent', 'enforce_context_line_budget', 'faq_id', 'faq_metrics_store', 'find_safe_faq_match', 'firestore_conversation_id', 'flow_match_title', 'gender_ack_message', 'gender_acknowledgement', 'get_bot_chat_response', 'get_canonical_user_id_and_phone', 'get_conversation_context_for_gpt', 'get_conversation_last_ai_response_at', 'get_dynamic_message', 'get_last_bot_message_for_gpt_context', 'gpt_response_data', 'initial_user_query_to_process_original', 'is_dynamic_retrieval_available', 'is_initial_message_for_gpt', 'is_post_takeover_escalation_cooldown', 'is_price_intent', 'is_reschedule_intent', 'is_smart', 'last_ai_response_at', 'last_bot_msg', 'last_text', 'local_qa_service', 'log_interaction', 'match_result', 'match_score', 'match_tier', 'merged', 'operational_context', 'orig_q', 'pending_clarification', 'qa_pair', 'qa_response', 'qa_steps', 'query_pre_set_from_booking_confirmation', 'query_to_send_to_gpt', 'respectful_address', 'response_language', 'retrieve_and_merge', 'save_conversation_message_to_firestore', 'save_for_training_conversation_log', 'selector_query', 'send_message_func', 'stored_language', 'takeover_ctx', 'update_dashboard_metric_in_firestore', 'user_data', 'user_id', 'user_image_base64', 'user_image_format', 'user_input_to_process', 'user_name', 'voice_meta']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
