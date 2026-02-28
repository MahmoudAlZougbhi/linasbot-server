# handlers/text_handlers_message.py
# Main message handler for WhatsApp text messages

from handlers.text_handlers_firestore import *
from handlers.text_handlers_firestore import get_message_merge_lock
from handlers.text_handlers_delayed import _delayed_process_messages


_EXPLICIT_HUMAN_HANDOFF_PATTERNS = [
    r"\b(human|agent|representative|operator|customer\s*service|someone\s+real)\b",
    r"\b(talk|speak|transfer|connect|escalate)\b.{0,20}\b(human|agent|representative|operator|someone)\b",
    r"\b(call\s+(me|us|please|now|back)|phone\s+call|callback)\b",
    r"(بدي|بدي احكي|حولني|وديني|خليني)\s*(?:احكي\s*)?(?:مع|على)\s*(?:موظف|شخص|انسان|مدير|مسؤول|خدمة العملاء)",
    r"(اتصلوا|اتصل|دقوا|تواصلوا)\s*(?:فيي|بي|معي|معنا)?",
    r"(مش\s*بدي\s*(?:بوت|روبوت)|بدي\s*حدا\s*بشري|بدي\s*حدا\s*حقيقي)"
]


def _is_explicit_human_handoff_request(message: str) -> bool:
    """Detect direct customer request for human/call takeover."""
    message_text = (message or "").strip().lower()
    if not message_text:
        return False
    return any(re.search(pattern, message_text, re.IGNORECASE | re.UNICODE) for pattern in _EXPLICIT_HUMAN_HANDOFF_PATTERNS)


async def handle_message(user_id: str, user_name: str, user_input_text: str, user_data: dict, send_message_func, send_action_func, skip_firestore_save: bool = False):
    """
    Main message handler for WhatsApp text messages.
    Combines rapid messages and then processes them.
    
    Args:
        skip_firestore_save: If True, skips saving to Firestore (used when called from voice_handlers after already saving)
    """
    config.user_names[user_id] = user_name
    
    # Ensure defaultdicts are initialized for this user
    if user_id not in config.user_context:
        config.user_context[user_id] = deque(maxlen=config.MAX_CONTEXT_MESSAGES)
    if user_id not in config.user_pending_messages:
        config.user_pending_messages[user_id] = deque()
    if user_id not in config.user_last_bot_response_time:
        config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    if user_id not in config.user_greeting_stage:
        config.user_greeting_stage[user_id] = 0
    # FIX: Only set to "unknown" if gender is not already a valid value
    # This prevents overwriting gender restored from Firestore after restart
    current_gender = config.user_gender.get(user_id)
    if current_gender not in ["male", "female"]:
        config.user_gender[user_id] = "unknown"
    if user_id not in config.gender_attempts:
        config.gender_attempts[user_id] = 0
    if user_id not in config.user_in_training_mode:
        config.user_in_training_mode[user_id] = False
    if user_id not in config.user_photo_analysis_count:
        config.user_photo_analysis_count[user_id] = 0
    if user_id not in config.user_in_human_takeover_mode:
        config.user_in_human_takeover_mode[user_id] = False

    # Check if user is in training mode
    if config.user_in_training_mode.get(user_id, False):
        print(f"[handle_message] INFO: User {user_id} in training mode. Handing over to handle_training_input.")
        await handle_training_input(
            user_id=user_id,
            user_input_text=user_input_text,
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func
        )
        return

    raw_msg = user_input_text.strip()

    if not raw_msg:
        print(f"[handle_message] ERROR: No usable text in message for user {user_id}. raw_msg is empty. Exiting.")
        return

    # ✅ FIXED: Only save to Firestore if not called from voice_handlers
    # Voice handler already saved the message with type="voice" and audio_url
    if not skip_firestore_save:
        # Save user's message to Firestore immediately
        current_conversation_id = user_data.get('current_conversation_id')
        phone_for_save = user_data.get('phone_number')

        # DEBUG: Log critical info before saving user message
        print(f"\n{'='*60}")
        print(f"🔍 HANDLE_MESSAGE: About to save USER message")
        print(f"   user_id: {user_id}")
        print(f"   current_conversation_id: {current_conversation_id}")
        print(f"   phone_number from user_data: {phone_for_save}")
        print(f"   phone_number from config: {config.user_data_whatsapp.get(user_id, {}).get('phone_number')}")
        print(f"   raw_msg preview: {raw_msg[:50] if raw_msg else 'None'}...")
        print(f"{'='*60}\n")

        source_message_id = user_data.pop("_source_message_id", None)
        message_metadata = {"type": "text"}
        if source_message_id:
            message_metadata["source_message_id"] = source_message_id

        await save_conversation_message_to_firestore(
            user_id,
            "user",
            raw_msg,
            current_conversation_id,
            user_name,
            phone_for_save,
            metadata=message_metadata,
        )

        # Update local user_data with the conversation_id (might have been created)
        new_conv_id = config.user_data_whatsapp[user_id].get('current_conversation_id')
        print(f"📍 After save: conversation_id is now: {new_conv_id}")
        user_data['current_conversation_id'] = new_conv_id
    else:
        print(f"[handle_message] INFO: Skipping Firestore save (called from voice_handler with skip_firestore_save=True)")
        # Just ensure current_conversation_id is up-to-date
        if 'current_conversation_id' not in user_data or not user_data['current_conversation_id']:
            user_data['current_conversation_id'] = config.user_data_whatsapp[user_id].get('current_conversation_id')

    current_conversation_id = user_data.get('current_conversation_id')
    
    # Get Firestore DB instance for sentiment and takeover checks
    db = get_firestore_db()

    async def _trigger_human_takeover(
        trigger_source: str,
        escalation_reason: str,
        customer_message: str,
        escalation_score: float = None,
        detected_issues: list = None
    ):
        """Mark conversation as waiting_human, notify admins, and write audit event."""
        if db and current_conversation_id:
            try:
                app_id_for_firestore = "linas-ai-bot-backend"
                conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                update_payload = {
                    "status": "waiting_human",
                    "human_takeover_active": True,
                    "human_takeover_requested": True,
                    "operator_id": None,
                    "escalation_reason": escalation_reason,
                    "escalation_time": datetime.datetime.now()
                }
                if escalation_score is not None:
                    update_payload["escalation_score"] = escalation_score
                if detected_issues:
                    update_payload["detected_issues"] = detected_issues

                conv_doc_ref.update(update_payload)
                print(f"✅ Conversation marked as waiting_human in Firebase")
            except Exception as e:
                print(f"⚠️ Failed to mark conversation as waiting_human: {e}")

        config.user_in_human_takeover_mode[user_id] = True

        escalation_messages = {
            "ar": "شكراً لصبرك. سيتم تحويلك إلى أحد موظفينا قريباً. 🙏",
            "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏",
            "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏"
        }
        escalation_msg = escalation_messages.get(user_data.get('user_preferred_lang', 'ar'), escalation_messages['ar'])
        await send_message_func(user_id, escalation_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            escalation_msg,
            current_conversation_id,
            user_name,
            user_data.get('phone_number')
        )

        notify_human_on_whatsapp(
            user_name,
            config.user_gender.get(user_id, "unknown"),
            customer_message,
            type_of_notification=f"{trigger_source} - {escalation_reason}"
        )

        try:
            from services.human_takeover_notification_service import human_takeover_notification_service

            notify_result = await human_takeover_notification_service.notify_and_audit_handoff(
                user_id=user_id,
                user_gender=config.user_gender.get(user_id, "unknown"),
                customer_name=user_name,
                customer_phone=user_data.get('phone_number', 'Unknown'),
                escalation_reason=escalation_reason,
                last_message=customer_message,
                trigger_source=trigger_source,
                conversation_id=current_conversation_id,
                extra_details={
                    "escalation_score": escalation_score,
                    "detected_issues": detected_issues or []
                }
            )
            notification_result = notify_result.get("notification_result", {})
            if notification_result.get("success"):
                print(f"✅ Sent notifications to {notification_result.get('sent_count')} admin(s)")
            else:
                print(f"⚠️ Notification sending failed: {notification_result.get('error')}")
        except Exception as notify_error:
            print(f"⚠️ Error sending human takeover notifications: {notify_error}")
            import traceback
            traceback.print_exc()

    # Explicit user request for human/call gets immediate takeover
    if _is_explicit_human_handoff_request(raw_msg) and not config.user_in_human_takeover_mode.get(user_id, False):
        print(f"📞 Explicit human/call handoff requested by user {user_id}")
        await _trigger_human_takeover(
            trigger_source="customer_explicit_request",
            escalation_reason="customer_requested_human",
            customer_message=raw_msg,
            escalation_score=100,
            detected_issues=["explicit_human_request_or_call"]
        )
        log_report_event("human_handover", user_id, config.user_gender.get(user_id, "unknown"), {
            "message": raw_msg,
            "status": "direct_keyword_trigger",
            "reason": "customer_requested_human"
        })
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        return
    
    # Analyze sentiment and check if auto-escalation is needed
    sentiment_analysis = sentiment_service.analyze_sentiment(
        user_id=user_id,
        message=raw_msg,
        language=user_data.get('user_preferred_lang', 'ar')
    )
    
    # Update conversation sentiment in Firebase
    if db and user_data.get('current_conversation_id'):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(user_data['current_conversation_id'])
            conv_doc_ref.update({
                "sentiment": sentiment_analysis["sentiment"],
                "last_updated": datetime.datetime.now()
            })
            print(f"✅ Updated conversation sentiment to: {sentiment_analysis['sentiment']}")
        except Exception as e:
            print(f"⚠️ Failed to update sentiment in Firebase: {e}")
    
    # Auto-escalate if needed
    if sentiment_analysis["should_escalate"] and not config.user_in_human_takeover_mode.get(user_id, False):
        print(f"🚨 AUTO-ESCALATION TRIGGERED for user {user_id}")
        print(f"   Reason: {sentiment_analysis['escalation_reason']}")
        print(f"   Score: {sentiment_analysis['escalation_score']}")
        print(f"   Issues: {sentiment_analysis['detected_issues']}")
        await _trigger_human_takeover(
            trigger_source="sentiment_auto_escalation",
            escalation_reason=sentiment_analysis['escalation_reason'],
            customer_message=raw_msg,
            escalation_score=sentiment_analysis['escalation_score'],
            detected_issues=sentiment_analysis['detected_issues']
        )
        
        # Log the escalation
        log_report_event("auto_escalation", user_id, config.user_gender.get(user_id, "unknown"), {
            "message": raw_msg,
            "reason": sentiment_analysis['escalation_reason'],
            "score": sentiment_analysis['escalation_score'],
            "issues": sentiment_analysis['detected_issues']
        })
        
        # Update metrics
        await update_dashboard_metric_in_firestore(user_id, "auto_escalations", 1)
        return

    # Check Firestore for human takeover status
    if db and user_data.get('current_conversation_id'):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(user_data['current_conversation_id'])
            doc_snap = conv_doc_ref.get()
            if doc_snap.exists:
                conv_data = doc_snap.to_dict()
                config.user_in_human_takeover_mode[user_id] = conv_data.get('human_takeover_active', False)
                if config.user_in_human_takeover_mode[user_id]:
                    print(f"[handle_message] INFO: User {user_id} conversation {user_data['current_conversation_id']} is in human takeover mode. AI will not respond.")
                    if not user_data.get('notified_human_takeover'):
                        # Get operator info for notification message
                        operator_name = conv_data.get('operator_name')
                        if not operator_name:
                            operator_id = conv_data.get('operator_id')
                            # If operator_id looks like an email, extract the name part
                            if operator_id and '@' in str(operator_id):
                                operator_name = str(operator_id).split('@')[0].replace('.', ' ').replace('_', ' ').title()
                            elif operator_id:
                                operator_name = operator_id

                        # Prepare handover notification message based on language
                        user_lang = user_data.get('user_preferred_lang', 'ar')

                        # Different messages depending on whether we have the operator name
                        if operator_name:
                            handover_messages = {
                                "ar": f"📞 تم تحويل المحادثة إلى {operator_name}. سيقوم بالرد عليك قريباً.",
                                "en": f"📞 The conversation has been transferred to {operator_name}. They will respond to you shortly.",
                                "fr": f"📞 La conversation a été transférée à {operator_name}. Il vous répondra sous peu."
                            }
                        else:
                            handover_messages = {
                                "ar": "📞 تم تحويل المحادثة إلى أحد موظفينا. سيقوم فريقنا بالرد عليك قريباً.",
                                "en": "📞 The conversation has been transferred to a human agent. Our team will respond to you shortly.",
                                "fr": "📞 La conversation a été transférée à un agent humain. Notre équipe vous répondra sous peu."
                            }
                        handover_msg = handover_messages.get(user_lang, handover_messages['ar'])

                        await send_message_func(user_id, handover_msg)
                        user_data['notified_human_takeover'] = True
                    return
            else:
                print(f"WARNING: Conversation {user_data['current_conversation_id']} not found in Firestore during takeover check.")
        except Exception as e:
            print(f"❌ ERROR checking human takeover status from Firestore for user {user_id}: {e}")

    # Check if it's the very first message after start
    if config.user_greeting_stage[user_id] == 1 and not config.user_gender.get(user_id):
        common_greetings_only = ["hi", "hello", "مرحبا", "سلام", "اهلين", "صباح الخير", "مساء الخير", "كيفك", "كيف الحال", "kifak", "shu", "bonjour", "salut", "bade", "sheel", "shil", "ana", "ta3ite" ]
        is_only_greeting = any(g == raw_msg.lower().strip() for g in common_greetings_only)

        if not is_only_greeting:
            if user_data['initial_user_query_to_process'] is None:
                user_data['initial_user_query_to_process'] = raw_msg
        else:
            user_data['initial_user_query_to_process'] = None

    # Language detection is now handled BEFORE GPT call by language_detection_service
    # The LanguageResolver detects language on each message using heuristics (Arabic script, Franco-Arabic, French/English markers)
    # GPT is then instructed to respond in the detected language
    print(f"[handle_message] 🌐 Language will be detected pre-GPT by language_detection_service for user {user_id}")

    # Message combining logic: wait 3s after LAST message, merge all, send ONE reply.
    # Concurrency-safe for WhatsApp webhook (multiple rapid messages).
    lock = await get_message_merge_lock(user_id)
    async with lock:
        config.user_pending_messages[user_id].append(raw_msg)

        # Cancel any previously scheduled processing task (reset timer: 3s after THIS last message)
        if user_id in _delayed_processing_tasks and not _delayed_processing_tasks[user_id].done():
            _delayed_processing_tasks[user_id].cancel()

        # Schedule a new processing task
        _delayed_processing_tasks[user_id] = asyncio.create_task(
            _delayed_process_messages(user_id, user_data, send_message_func, send_action_func)
        )
