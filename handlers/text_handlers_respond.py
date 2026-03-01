# handlers/text_handlers_respond.py
# Core logic for processing user input and generating bot responses

from handlers.text_handlers_firestore import *
from services.analytics_events import analytics
from services.language_detection_service import language_detection_service
from services.interaction_flow_logger import log_interaction
from utils.datetime_utils import detect_reschedule_intent
import time

PRICE_INTENT_KEYWORDS = [
    "price",
    "cost",
    "how much",
    "pricing",
    "سعر",
    "اسعار",
    "كم",
    "قديش",
    "أديش",
    "تكلفة",
    "prix",
    "coût",
    "combien",
    "tarif",
    "adesh",
    "adde",
    "2adde",
    "2adesh",
    "kam",
    "sa3er",
]


def _is_price_intent(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in PRICE_INTENT_KEYWORDS)


async def _process_and_respond(user_id: str, user_name: str, user_input_to_process: str, user_data: dict, send_message_func, send_action_func):
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    # Start timing for response time tracking
    start_time = time.time()
    
    current_gender = config.user_gender.get(user_id, "unknown")
    current_preferred_lang = user_data.get('user_preferred_lang', 'ar')
    current_conversation_id = user_data.get('current_conversation_id')

    # ===== PRE-GPT LANGUAGE DETECTION =====
    is_expecting_name = user_data.get('awaiting_name_input', False)
    lang_result = language_detection_service.detect_language(
        user_id=user_id,
        message=user_input_to_process,
        user_data=user_data,
        is_expecting_name=is_expecting_name
    )

    # Update language variables
    current_preferred_lang = lang_result['detected_language']
    response_language = lang_result['response_language']

    print(f"[_process_and_respond] 🌐 Language detected: {current_preferred_lang} → respond in: {response_language}")
    # =====================================

    # DEBUG: Log gender state at start of processing
    print(f"[_process_and_respond] 🔍 USER STATE for {user_id}:")
    print(f"   - current_gender: '{current_gender}'")
    print(f"   - greeting_stage: {config.user_greeting_stage.get(user_id, 0)}")
    print(f"   - gender_attempts: {config.gender_attempts.get(user_id, 0)}")
    
    # 📊 ANALYTICS: Log user's message
    analytics.log_message(
        source="user",
        msg_type="text",
        user_id=user_id,
        language=current_preferred_lang,
        sentiment="neutral",
        message_length=len(user_input_to_process)
    )

    # NEW: Check if we're awaiting name input after gender confirmation
    if user_data.get('awaiting_name_input', False):
        print(f"🔔 Received name input from user {user_id}: '{user_input_to_process}'")

        # Extract actual name from common phrases
        def extract_name_from_input(text):
            """Extract the actual name from phrases like 'my name is jad', 'ana ismi jad', etc."""
            text = text.strip()
            text_lower = text.lower()

            # Patterns to extract name from - MUST start at beginning of string (^)
            # This prevents matching partial words in the middle of a name
            patterns = [
                # English patterns
                r"^(?:my name is|i'm|i am|im|it's|its|call me|they call me|name's)\s+(.+)",
                # Franco-Arabic patterns (common ways to say "my name is" in Franco)
                r"^(?:ana ismi|ana esmi|ana isme|ismi|esmi|isme|esme)\s+(.+)",
                # French patterns - handle all apostrophe variations:
                # - je m'appelle (proper)
                # - je mappelle (no apostrophe - common typing)
                # - je m appelle (space instead of apostrophe)
                r"^(?:je\s*m['\s]?appelle|je suis|mon nom est|c'est|moi c'est)\s+(.+)",
            ]

            for pattern in patterns:
                match = re.match(pattern, text_lower)  # Use re.match instead of re.search
                if match:
                    # Get the name part, preserving original case from input
                    name_start = match.start(1)
                    name_end = match.end(1)
                    # Find corresponding position in original text
                    extracted = text[name_start:name_end].strip()
                    # Clean up punctuation at the end
                    extracted = re.sub(r'[.,!?]+$', '', extracted).strip()
                    if extracted:
                        print(f"DEBUG: Extracted name '{extracted}' from phrase '{text}'")
                        return extracted

            # Arabic patterns (separate due to RTL) - also anchor to start
            arabic_patterns = [
                r'^(?:اسمي|انا اسمي|انا)\s+(.+)',
            ]
            for pattern in arabic_patterns:
                match = re.match(pattern, text)  # Use re.match
                if match:
                    extracted = match.group(1).strip()
                    extracted = re.sub(r'[.,!?،؟]+$', '', extracted).strip()
                    if extracted:
                        print(f"DEBUG: Extracted Arabic name '{extracted}' from phrase '{text}'")
                        return extracted

            # No pattern matched - return original (user just typed their name)
            print(f"DEBUG: No prefix pattern matched, using full input as name: '{text}'")
            return text

        extracted_name = extract_name_from_input(user_input_to_process)
        
        # Basic validation: name should be 2-50 characters, letters/spaces/hyphens/apostrophes only
        name_pattern = r'^[A-Za-z\u00C0-\u00FF\u0600-\u06FF\s\-\']+$'
        if 2 <= len(extracted_name) <= 50 and re.match(name_pattern, extracted_name, re.UNICODE):
            # Save the name to memory
            config.user_names[user_id] = extracted_name
            print(f"✅ Saved name '{extracted_name}' to memory for user {user_id}")
            
            # CRITICAL: Save to user_data to prevent webhook from overwriting
            user_data['collected_name'] = extracted_name
            user_data['name_source'] = 'user_provided'
            print(f"✅ Protected name in user_data: {extracted_name}")
            
            # Save to Firestore user document
            db = get_firestore_db()
            if db:
                try:
                    app_id_for_firestore = "linas-ai-bot-backend"
                    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
                    user_doc_ref.update({
                        "name": extracted_name,
                        "last_updated": datetime.datetime.now()
                    })
                    print(f"✅ Saved name '{extracted_name}' to Firestore for user {user_id}")
                except Exception as e:
                    print(f"⚠️ Failed to save name to Firestore: {e}")
            
            # Clear the awaiting flag
            user_data['awaiting_name_input'] = False
            
            # Mark greeting stage as complete
            config.user_greeting_stage[user_id] = 2
            print(f"✅ Greeting stage set to 2 for user {user_id}")
            
            # Send acknowledgment with the name
            thanks_messages = {
                "ar": f"شكراً {extracted_name}! 😊 كيف بقدر ساعدك اليوم؟",
                "en": f"Thanks, {extracted_name}! 😊 How can I help you today?",
                "fr": f"Merci, {extracted_name}! 😊 Comment puis-je vous aider aujourd'hui?",
                "franco": f"شكراً {extracted_name}! 😊 كيف فيني ساعدك اليوم؟"
            }
            
            thanks_message = thanks_messages.get(current_preferred_lang, thanks_messages["ar"])
            await send_message_func(user_id, thanks_message)
            await save_conversation_message_to_firestore(user_id, "ai", thanks_message, current_conversation_id, extracted_name, user_data.get('phone_number'))
            
            # Log the event
            log_report_event("name_saved", extracted_name, current_gender, {"method": "Post-Gender Confirmation", "whatsapp_id": user_id})
            
            return
        else:
            # Invalid name format
            print(f"⚠️ Invalid name format from user {user_id}: '{extracted_name}'")
            
            error_messages = {
                "ar": "عذراً، الاسم يجب أن يحتوي على حر��ف فقط. ممكن تكتب اسمك الكامل مرة تانية؟",
                "en": "Sorry, the name should contain only letters. Could you write your full name again?",
                "fr": "Désolé, le nom ne doit contenir que des lettres. Pourriez-vous écrire votre nom complet à nouveau?",
                "franco": "عذراً، الاسم لازم يكون حروف بس. ممكن تكتب اسمك الكامل مرة تانية؟"
            }
            
            error_message = error_messages.get(current_preferred_lang, error_messages["ar"])
            await send_message_func(user_id, error_message)
            await save_conversation_message_to_firestore(user_id, "ai", error_message, current_conversation_id, user_name, user_data.get('phone_number'))
            
            return

    # Check if human takeover is active
    if config.user_in_human_takeover_mode.get(user_id, False):
        print(f"[_process_and_respond] INFO: Conversation {current_conversation_id} for user {user_id} is in human takeover mode. AI will not respond.")
        return

    is_initial_message_for_gpt = (config.user_greeting_stage[user_id] == 1) and (current_gender == "unknown")
    initial_user_query_to_process_original = user_data.get('initial_user_query_to_process')

    awaiting_confirmation = user_data.get('awaiting_human_handover_confirmation', False)
    confirmation_keywords_ar = ["اه", "نعم", "اي", "ايه", "يا ريت", "خلصني", "موافق", "yes", "oui", "ok", "تمام"]
    rejection_keywords_ar = ["لا", "ما بدي", "خليني معك", "مش ضروري", "no", "non"]

    gpt_response_data = {}

    if awaiting_confirmation:
        user_input_lower = user_input_to_process.lower()
        if any(kw in user_input_lower for kw in confirmation_keywords_ar):
            gpt_response_data = {
                "action": "human_handover_confirmed",
                "bot_reply": "تمام، تم إرسال طلبك! رح يتواصل معك حدا من فريقنا بأقرب وقت ممكن. شكراً لتفهمك! 👋",
                "detected_language": current_preferred_lang,
                "detected_gender": current_gender if current_gender != "unknown" else None,
                "current_gender_from_config": current_gender
            }
            user_data['awaiting_human_handover_confirmation'] = False
        elif any(kw in user_input_lower for kw in rejection_keywords_ar):
            gpt_response_data = {
                "action": "return_to_normal_chat",
                "bot_reply": "تمام، ك��ف بقدر أساعدك الآن؟",
                "detected_language": current_preferred_lang,
                "detected_gender": current_gender if current_gender != "unknown" else None,
                "current_gender_from_config": current_gender
            }
            user_data['awaiting_human_handover_confirmation'] = False
        else:
            conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)
            gpt_response_data = await get_bot_chat_response(
                user_id=user_id,
                user_input=user_input_to_process,
                current_context_messages=conversation_history,
                current_gender=current_gender,
                current_preferred_lang=current_preferred_lang,
                response_language=response_language,
                is_initial_message_after_start=is_initial_message_for_gpt,
                initial_user_query_to_process=initial_user_query_to_process_original
            )

    else:
        query_to_send_to_gpt = user_input_to_process

        # DEBUG: Gender confirmation and original query retrieval
        print(f"[_process_and_respond] 🔍 Gender Check:")
        print(f"  - current_gender: {current_gender}")
        print(f"  - greeting_stage: {config.user_greeting_stage[user_id]}")
        print(f"  - initial_query: {initial_user_query_to_process_original}")

        if current_gender in ["male", "female"] and config.user_greeting_stage[user_id] == 1 and initial_user_query_to_process_original:
            print(f"[_process_and_respond] ✅ Gender confirmed! Answering original query: '{initial_user_query_to_process_original}'")
            user_data['initial_user_query_to_process'] = None
            query_to_send_to_gpt = initial_user_query_to_process_original
            config.user_greeting_stage[user_id] = 2
            is_initial_message_for_gpt = False

            gender_acknowledgement = "أهلاً بك أستاذ " if current_gender == "male" else "أهلاً بكِ سيدتي "
            await send_message_func(user_id, f"{gender_acknowledgement}{user_name}! شكراً لتحديد جنسك. سأجيب على استفسارك الأصلي.")
            await save_conversation_message_to_firestore(user_id, "ai", f"{gender_acknowledgement}{user_name}! شكراً لتحديد جنسك. سأجيب على استفسارك الأصلي.", current_conversation_id, user_name, user_data.get('phone_number'))

        # Check Q&A Database before calling GPT-4
        # Decision flow: 90%+ returns Q&A directly, <90% passes to GPT with top 3 relevant Q&A pairs
        print(f"[_process_and_respond] 🔍 Checking Q&A DATABASE for: '{query_to_send_to_gpt}'")

        is_reschedule_intent = detect_reschedule_intent(query_to_send_to_gpt)
        is_price_intent = _is_price_intent(query_to_send_to_gpt)
        if is_reschedule_intent:
            # Routing safeguard: postpone/reschedule requests should never be short-circuited to Q&A.
            print(f"[_process_and_respond] 🔁 Reschedule intent detected. Skipping direct Q&A routing.")
            match_result = None
        elif is_price_intent:
            # Pricing must come from system/API sync path, never from static Q&A text.
            print(f"[_process_and_respond] 💰 Price intent detected. Skipping direct Q&A routing for exact system pricing.")
            match_result = None
        else:
            match_result = await local_qa_service.find_match_with_tier(query_to_send_to_gpt, current_preferred_lang)

        if match_result:
            # 90%+ match: Return Q&A directly
            match_score = match_result.get("match_score", 0)
            qa_pair = match_result.get("qa_pair", {})
            qa_response = qa_pair.get("answer", "")

            print(f"[_process_and_respond] ✅ Q&A MATCH FOUND!")
            print(f"[_process_and_respond] 📊 Match Score: {match_score:.0%} (≥90% threshold)")
            print(f"[_process_and_respond] 🎯 Returning Q&A directly")
            print(f"[_process_and_respond] 💰 AI CREDITS SAVED: $0.02-0.05 (NO GPT-4 CALL)")
            print(f"[_process_and_respond] ⚡ Response Time: ~100-200ms (vs 2-5s with GPT-4)")
            print(f"[_process_and_respond] 🎯 Answer: {qa_response[:100]}...")

            await send_message_func(user_id, qa_response)
            await save_conversation_message_to_firestore(
                user_id, "ai", qa_response,
                current_conversation_id, user_name,
                user_data.get('phone_number'),
                metadata={
                    "source": "qa_database",
                    "match_score": match_score,
                    "ai_cost_saved": True,
                    "response_type": "instant"
                }
            )
            await update_dashboard_metric_in_firestore(user_id, "qa_responses_used", 1)
            config.user_greeting_stage[user_id] = 2
            save_for_training_conversation_log(query_to_send_to_gpt, qa_response)
            log_interaction(user_id, query_to_send_to_gpt, qa_response, "qa_database", qa_match_score=match_score)
            return
        else:
            # <90% match: GPT + knowledge + style + top 3 relevant Q&A pairs
            print(f"[_process_and_respond] ℹ️ No Q&A match found (below 90%). Proceeding with GPT-4...")
            print(f"[_process_and_respond] 💡 GPT will receive top 3 relevant Q&A pairs in context")

            # Dynamic retrieval: if content files exist, use file selection + merged content (reduces tokens)
            custom_context = None
            try:
                from services.dynamic_retrieval_service import (
                    is_dynamic_retrieval_available,
                    retrieve_and_merge,
                )
                if is_dynamic_retrieval_available() and not is_reschedule_intent:
                    merged, clarification, action = await retrieve_and_merge(
                        query_to_send_to_gpt,
                        include_price_hint=is_price_intent,
                    )
                    if action == "ask_clarification" and clarification:
                        await send_message_func(user_id, clarification)
                        await save_conversation_message_to_firestore(user_id, "ai", clarification, current_conversation_id, user_name, user_data.get("phone_number"))
                        save_for_training_conversation_log(query_to_send_to_gpt, clarification)
                        log_interaction(user_id, query_to_send_to_gpt, clarification, "dynamic_retrieval")
                        return
                    custom_context = merged
                    print(f"[_process_and_respond] 📂 Dynamic retrieval: action={action}, context_len={len(merged) if merged else 0}")
            except Exception as e:
                print(f"[_process_and_respond] ⚠️ Dynamic retrieval fallback: {e}")

            conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)

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
            )

    action = gpt_response_data.get("action")
    bot_reply_text = gpt_response_data.get("bot_reply")
    detected_gender_from_gpt = gpt_response_data.get("detected_gender")
    detected_language = gpt_response_data.get("detected_language")
    escalation_reason_from_gpt = gpt_response_data.get("escalation_reason")
    flow_meta = gpt_response_data.get("_flow_meta") or {}

    async def _activate_ai_handover(escalation_reason: str, trigger_source: str):
        """Switch conversation to waiting_human, notify admins from settings, and write audit."""
        db = get_firestore_db()
        if db and current_conversation_id:
            try:
                app_id_for_firestore = "linas-ai-bot-backend"
                conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                conv_doc_ref.update({
                    "status": "waiting_human",
                    "human_takeover_active": True,
                    "human_takeover_requested": True,
                    "operator_id": None,
                    "escalation_reason": escalation_reason,
                    "escalation_time": datetime.datetime.now(),
                    "last_updated": datetime.datetime.now()
                })
                print(f"✅ Conversation {current_conversation_id} set to waiting_human (AI decision)")
            except Exception as e:
                print(f"⚠️ Failed to update handover state in Firestore: {e}")

        config.user_in_human_takeover_mode[user_id] = True

        notify_human_on_whatsapp(
            user_name,
            current_gender,
            user_input_to_process,
            type_of_notification=f"AI handover - {escalation_reason}"
        )

        try:
            from services.human_takeover_notification_service import human_takeover_notification_service
            await human_takeover_notification_service.notify_and_audit_handoff(
                user_id=user_id,
                user_gender=current_gender,
                customer_name=user_name,
                customer_phone=user_data.get('phone_number', 'Unknown'),
                escalation_reason=escalation_reason,
                last_message=user_input_to_process,
                trigger_source=trigger_source,
                conversation_id=current_conversation_id,
                extra_details={"action": action}
            )
        except Exception as notify_error:
            print(f"⚠️ Failed to send AI handoff template/audit: {notify_error}")

    # Update language from GPT's detection
    if detected_language and detected_language in ['en', 'ar', 'fr', 'franco']:
        previous_lang = user_data.get('user_preferred_lang', 'ar')
        if previous_lang != detected_language:
            user_data['user_preferred_lang'] = detected_language
            user_persistence.save_user_language(user_id, detected_language)
            print(f"[_process_and_respond] 🌐 Language updated by GPT: {previous_lang} → {detected_language}")
        else:
            print(f"[_process_and_respond] 🌐 Language confirmed by GPT: {detected_language}")
        # Update local variable so all follow-up messages in this function use the detected language
        current_preferred_lang = detected_language

    if detected_gender_from_gpt and config.user_gender.get(user_id) != detected_gender_from_gpt:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "User Input Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=user_name)
    elif detected_gender_from_gpt and config.user_gender.get(user_id) == "unknown" and detected_gender_from_gpt in ["male", "female"]:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "GPT Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=user_name)

    # Track what we send for flow logging
    sent_reply = bot_reply_text

    # Process the action requested by GPT
    if action in ["initial_greet_and_ask_gender", "ask_gender"]:
        if current_gender in ["male", "female"]:
            # FIX: Gender is already known, but GPT tried to ask for it
            # Override the action and provide a helpful response instead
            print(f"⚠️ OVERRIDE: GPT action was '{action}' but gender is already '{current_gender}'. Changing response.")
            override_reply_messages = {
                "ar": "كيف فيني ساعدك اليوم؟",
                "en": "How can I help you today?",
                "fr": "Comment puis-je vous aider aujourd'hui?",
                "franco": "كيف فيني ساعدك اليوم؟"
            }
            override_reply = override_reply_messages.get(current_preferred_lang, override_reply_messages["ar"])
            sent_reply = override_reply
            await send_message_func(user_id, override_reply)
            await save_conversation_message_to_firestore(user_id, "ai", override_reply, current_conversation_id, user_name, user_data.get('phone_number'))
        else:
            config.gender_attempts[user_id] += 1
            if config.gender_attempts[user_id] >= config.MAX_GENDER_ASK_ATTEMPTS:
                fallback_reply = "عذراً، لم أتمكن من تحديد جنسك بشكل دقيق. لتقديم أفضل مساعدة، قد تحتاج للتواصل مع فريقنا مباشرة. أو يمكنك المحاولة مجدداً بعبارة واضحة كـ 'أنا شب' أو 'أنا صبية'."
                sent_reply = fallback_reply
                await send_message_func(user_id, fallback_reply)
                await save_conversation_message_to_firestore(user_id, "ai", fallback_reply, current_conversation_id, user_name, user_data.get('phone_number'))
                config.user_greeting_stage[user_id] = 2
            else:
                await send_message_func(user_id, bot_reply_text)
                await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))

    elif action == "confirm_gender":
        # FIXED: Don't send GPT's reply to avoid double messages
        # Save the confirmed gender permanently
        if detected_gender_from_gpt and detected_gender_from_gpt in ["male", "female"]:
            await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_data.get('phone_number', user_id), name=user_name)
            print(f"✅ Saved gender '{detected_gender_from_gpt}' for user {user_id} to API")

        # Check if there's a stored initial question to answer
        initial_query = user_data.get('initial_user_query_to_process')
        if initial_query:
            print(f"🔔 User {user_id} confirmed gender. Found initial query to answer: '{initial_query}'")

            # Clear the initial query and update greeting stage
            user_data['initial_user_query_to_process'] = None
            config.user_greeting_stage[user_id] = 2

            # Get GPT response for the initial query
            conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)
            initial_query_response = await get_bot_chat_response(
                user_id=user_id,
                user_input=initial_query,
                current_context_messages=conversation_history,
                current_gender=detected_gender_from_gpt or current_gender,
                current_preferred_lang=current_preferred_lang,
                response_language=response_language,
                is_initial_message_after_start=False,
                initial_user_query_to_process=None
            )

            initial_query_answer = initial_query_response.get("bot_reply", "")

            # Prepare acknowledgment based on language
            acknowledgement_messages = {
                "ar": "شكراً لتحديد جنسك! للإجابة على سؤالك الأولي:\n\n",
                "en": "Thanks for letting me know! To answer your initial question:\n\n",
                "fr": "Merci de m'avoir informé! Pour répondre à votre question initiale:\n\n",
                "franco": "شكراً! للإجابة على سؤالك:\n\n"
            }

            acknowledgement = acknowledgement_messages.get(current_preferred_lang, acknowledgement_messages["ar"])
            combined_response = acknowledgement + initial_query_answer
            sent_reply = combined_response

            await send_message_func(user_id, combined_response)
            await save_conversation_message_to_firestore(user_id, "ai", combined_response, current_conversation_id, user_name, user_data.get('phone_number'))
            print(f"✅ Answered initial query for user {user_id}")
        else:
            # No initial query stored, ask for name
            print(f"🔔 User {user_id} confirmed gender. No initial query found, asking for name.")

            name_question_messages = {
                "ar": "رائع! والآن، ما هو اسمك الكامل لو سمحت؟",
                "en": "Great! And now, may I have your full name please?",
                "fr": "Super! Et maintenant, puis-je avoir votre nom complet s'il vous plaît?",
                "franco": "رائع! والآن، شو اسمك الكامل لو سمحت؟"
            }

            name_question = name_question_messages.get(current_preferred_lang, name_question_messages["ar"])
            sent_reply = name_question
            await send_message_func(user_id, name_question)
            await save_conversation_message_to_firestore(user_id, "ai", name_question, current_conversation_id, user_name, user_data.get('phone_number'))

            # Set flag to expect name in next message
            user_data['awaiting_name_input'] = True
            print(f"🔔 User {user_id} now awaiting name input.")

    elif action == "confirm_booking_details":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))
        config.user_greeting_stage[user_id] = 2

    elif action == "human_handover_initial_ask":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))
        user_data['awaiting_human_handover_confirmation'] = True

    elif action == "human_handover_confirmed":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))
        await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "customer_requested_human",
            trigger_source="ai_handover_confirmed"
        )
        log_report_event("human_handover", user_id, current_gender, {
            "message": user_input_to_process,
            "status": "confirmed",
            "source": "ai_handover_confirmed"
        })
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)

    elif action == "return_to_normal_chat":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))

    elif action == "human_handover":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))
        await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "ai_decided_handoff",
            trigger_source="ai_handover_direct"
        )
        log_report_event("human_handover", user_id, current_gender, {
            "message": user_input_to_process,
            "status": "direct",
            "source": "ai_handover_direct"
        })
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)

    elif action in ["answer_question", "normal_chat", "unknown_query", "provide_info", "tool_call", "ask_for_details_for_booking", "ask_for_service_type", "ask_for_details", "ask_for_tattoo_photo", "check_customer_status", "confirm_appointment_reschedule"]:
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'))
        config.user_greeting_stage[user_id] = 2

    else:
        sent_reply = "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى."
        await send_message_func(user_id, sent_reply)
        await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'))
        print(f"[_process_and_respond] ERROR: User {user_id} received fallback reply due to unexpected action: {action}")

    # Flow logging for dashboard transparency
    response_time_ms = (time.time() - start_time) * 1000
    flow_source = "rate_limit" if action == "rate_limit_exceeded" else "moderation" if action == "content_moderated" else "gpt"
    log_interaction(
        user_id,
        user_input_to_process,
        sent_reply or "",
        flow_source,
        ai_query_summary=flow_meta.get("ai_query_summary"),
        ai_raw_response=flow_meta.get("ai_raw_response"),
        model=flow_meta.get("model"),
        tokens=flow_meta.get("tokens"),
        response_time_ms=response_time_ms,
        tool_calls=flow_meta.get("tool_calls"),
    )

    # Token counting and cost calculation
    prompt_tokens = 0
    completion_tokens = 0
    cost = 0.0
    
    if user_input_to_process.strip() and not user_input_to_process.lower().startswith('/start'):
        prompt_tokens = count_tokens(get_system_instruction(user_id, current_preferred_lang) + "\n\n" + user_input_to_process)
        completion_tokens = count_tokens(bot_reply_text)
        total_tokens = prompt_tokens + completion_tokens
        cost = (prompt_tokens / 1_000_000 * 5) + (completion_tokens / 1_000_000 * 15)
        print(f"[_process_and_respond] 🔹 Prompt tokens: {prompt_tokens}")
        print(f"[_process_and_respond] 🔹 Completion tokens: {completion_tokens}")
        print(f"[_process_and_respond] 📊 Total tokens: {total_tokens} | 💰 Estimated cost: ${cost:.6f}\n")
        save_for_training_conversation_log(user_input_to_process, bot_reply_text)
    
    # 📊 ANALYTICS: Log bot's response with performance metrics
    response_time_ms = (time.time() - start_time) * 1000
    analytics.log_message(
        source="bot",
        msg_type="text",
        user_id=user_id,
        language=current_preferred_lang,
        sentiment="neutral",  # Could be enhanced with sentiment detection
        tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
        model="gpt-4o",
        response_time_ms=response_time_ms,
        message_length=len(bot_reply_text) if bot_reply_text else 0
    )
    
    # 📊 ANALYTICS: Log gender if detected
    if detected_gender_from_gpt and detected_gender_from_gpt in ["male", "female"]:
        analytics.log_gender(user_id, detected_gender_from_gpt)
    
    # 📊 ANALYTICS: Log escalation if human handover
    if action in ["human_handover", "human_handover_confirmed"]:
        analytics.log_escalation(
            user_id=user_id,
            escalation_type="human_handover",
            reason="user_requested"
        )
    
    # 📊 ANALYTICS: Detect and log service requests
    service_keywords = {
        "laser_hair_removal": ["hair removal", "إزالة الشعر", "ليزر الشعر", "شعر", "hair", "épilation"],
        "tattoo_removal": ["tattoo", "وشم", "tatouage", "remove tattoo", "إزالة وشم"],
        "co2_laser": ["co2", "acne", "حب الشباب", "acné", "skin treatment"],
        "skin_whitening": ["whitening", "تبييض", "blanchiment", "skin lightening"],
        "botox": ["botox", "بوتوكس"],
        "fillers": ["filler", "حشو", "remplissage"]
    }
    
    # Check user input and bot reply for service mentions
    combined_text = (user_input_to_process + " " + (bot_reply_text or "")).lower()
    
    for service, keywords in service_keywords.items():
        if any(keyword.lower() in combined_text for keyword in keywords):
            analytics.log_service_request(
                user_id=user_id,
                service=service
            )
            print(f"📊 Analytics: Detected service request - {service}")
            break  # Only log one service per message to avoid duplicates

    config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    return
