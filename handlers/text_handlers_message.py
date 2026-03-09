# handlers/text_handlers_message.py
# Main message handler for WhatsApp text messages
# Human handoff: AI detects intent (no keyword/regex - AI understands context)

from handlers.text_handlers_firestore import *
from handlers.text_handlers_delayed import _delayed_process_messages


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
                    "conversation_state": "waiting_for_operator",
                    "escalation_reason": escalation_reason,
                    "escalation_time": datetime.datetime.now(),
                    "last_updated": datetime.datetime.now(),
                }
                if escalation_score is not None:
                    update_payload["escalation_score"] = escalation_score
                if detected_issues:
                    update_payload["detected_issues"] = detected_issues

                conv_doc_ref.update(update_payload)
                print(f"✅ Conversation marked as waiting_human in Firebase")
                try:
                    from services.live_chat_service import live_chat_service
                    live_chat_service.invalidate_cache()
                    asyncio.create_task(live_chat_service._refresh_index_for_conversation(user_id, current_conversation_id))
                except Exception as idx_err:
                    print(f"⚠️ Index refresh after handover: {idx_err}")
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

    # Human handoff: AI detects intent (no keyword/regex matching - AI understands context)
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
                    operator_id = conv_data.get('operator_id')
                    user_lang = user_data.get('user_preferred_lang', 'ar')

                    if operator_id:
                        # User has an operator — send handover notification once
                        print(f"[handle_message] INFO: User {user_id} has operator. AI will not respond.")
                        if not user_data.get('notified_human_takeover'):
                            operator_name = conv_data.get('operator_name')
                            if not operator_name:
                                if operator_id and '@' in str(operator_id):
                                    operator_name = str(operator_id).split('@')[0].replace('.', ' ').replace('_', ' ').title()
                                else:
                                    operator_name = operator_id
                            handover_messages = {
                                "ar": f"📞 تم تحويل المحادثة إلى {operator_name}. سيقوم بالرد عليك قريباً.",
                                "en": f"📞 The conversation has been transferred to {operator_name}. They will respond to you shortly.",
                                "fr": f"📞 La conversation a été transférée à {operator_name}. Il vous répondra sous peu."
                            }
                            handover_msg = handover_messages.get(user_lang, handover_messages['ar'])
                            await send_message_func(user_id, handover_msg)
                            await save_conversation_message_to_firestore(
                                user_id, "ai", handover_msg, current_conversation_id,
                                user_name, user_data.get('phone_number')
                            )
                            user_data['notified_human_takeover'] = True
                    else:
                        # User is in waiting queue (no operator yet) — send "please wait" auto-reply with rate limiting
                        print(f"[handle_message] INFO: User {user_id} in waiting queue. Sending waiting auto-reply if cooldown passed.")
                        now = datetime.datetime.now()
                        last_sent = config.user_last_waiting_reply_sent.get(user_id, datetime.datetime.min)
                        try:
                            elapsed = (now - last_sent).total_seconds()
                        except (TypeError, ValueError):
                            elapsed = config.WAITING_REPLY_COOLDOWN_SECONDS + 1
                        if elapsed >= config.WAITING_REPLY_COOLDOWN_SECONDS:
                            waiting_messages = {
                                "ar": "شوي، منكون معك، شكراً لصبركم، عندنا شوي دقة 🙏",
                                "en": "Just a moment, we'll be with you shortly. Thank you for your patience 🙏",
                                "fr": "Un instant, nous serons avec vous sous peu. Merci pour votre patience 🙏"
                            }
                            waiting_msg = waiting_messages.get(user_lang, waiting_messages['ar'])
                            await send_message_func(user_id, waiting_msg)
                            await save_conversation_message_to_firestore(
                                user_id, "ai", waiting_msg, current_conversation_id,
                                user_name, user_data.get('phone_number')
                            )
                            config.user_last_waiting_reply_sent[user_id] = now
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

    # Message combining logic
    config.user_pending_messages[user_id].append(raw_msg)

    # Cancel any previously scheduled processing task
    if user_id in _delayed_processing_tasks and not _delayed_processing_tasks[user_id].done():
        _delayed_processing_tasks[user_id].cancel()

    # Schedule a new processing task
    _delayed_processing_tasks[user_id] = asyncio.create_task(
        _delayed_process_messages(user_id, user_data, send_message_func, send_action_func)
    )
