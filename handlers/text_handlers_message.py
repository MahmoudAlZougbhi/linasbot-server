# handlers/text_handlers_message.py
# Main message handler for WhatsApp text messages
# Human handoff: AI detects intent (no keyword/regex - AI understands context)

from handlers.text_handlers_firestore import *
from handlers.text_handlers_delayed import _delayed_process_messages
from services.dynamic_messages_service import get_dynamic_message

GREETING_INACTIVITY_SECONDS = 43200  # 12 hours


def _extract_greeting_from_style_content(style_content: str) -> str:
    """Extract a user-facing greeting sentence from a style file content."""
    if not style_content:
        return ""
    lines = [ln.strip() for ln in str(style_content).splitlines() if ln.strip()]
    # Prefer explicit example bot lines first.
    for ln in lines:
        lower = ln.lower()
        if lower.startswith("bot:") or lower.startswith("assistant:"):
            candidate = ln.split(":", 1)[1].strip()
            if candidate:
                return candidate
    # Fallback: first non-heading/non-rule line.
    for ln in lines:
        if ln.startswith("#") or ln.startswith("-") or ln.lower().startswith("rule"):
            continue
        if len(ln) >= 8:
            return ln
    return ""


def _get_session_greeting_message(user_lang: str = "ar") -> str:
    """
    Load greeting from Content Manager style files (title contains 'greeting').
    Falls back to router greeting templates when no suitable content is found.
    """
    try:
        from services import content_files_service as cfs
        titles = cfs.get_titles_only("style") or []
        greeting_candidates = []
        for t in titles:
            title = str(t.get("title", ""))
            if "greeting" in title.lower() or "ترحيب" in title.lower():
                greeting_candidates.append(t)

        # Prefer file language match first.
        def _lang_score(t):
            lang = (t.get("language") or "").lower()
            if lang == user_lang:
                return 2
            if lang in ("", "ar", "general"):
                return 1
            return 0

        greeting_candidates.sort(key=_lang_score, reverse=True)
        for t in greeting_candidates:
            data = cfs.get_file("style", t.get("id", ""))
            if not data:
                continue
            extracted = _extract_greeting_from_style_content(data.get("content", ""))
            if extracted:
                return extracted
    except Exception as e:
        print(f"[handle_message] ⚠️ Failed loading greeting from content manager: {e}")

    # Try dynamic messages catalog first
    dyn = get_dynamic_message("session_greeting_after_inactivity", user_lang)
    if dyn:
        return dyn

    # Final fallback
    try:
        from services.conversation_router import GREETING_TEMPLATES
        return GREETING_TEMPLATES.get(user_lang, GREETING_TEMPLATES["ar"])
    except Exception:
        return "مرحباً! 😊 كيف فيني ساعدك اليوم؟"


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

    # Per single-message guardrail: limit long pasted text to avoid excessive token usage.
    non_empty_line_count = len(
        [ln for ln in raw_msg.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    )
    if non_empty_line_count > config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE:
        await send_message_func(
            user_id,
            f"لطفاً خفّف طول الرسالة: الحد الأقصى للرسالة الواحدة هو {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE} سطر. "
            "قسّمها على أكثر من رسالة قصيرة."
        )
        print(
            f"[handle_message] Blocked long single message for user {user_id}: "
            f"{non_empty_line_count} lines (limit: {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE})"
        )
        return

    # Session timing for greeting policy (new conversation or inactivity >= 1h)
    now_ts = datetime.datetime.now()
    previous_user_msg_ts = user_data.get("last_user_message_at")
    inactivity_seconds = None
    if isinstance(previous_user_msg_ts, datetime.datetime):
        inactivity_seconds = (now_ts - previous_user_msg_ts).total_seconds()
    user_data["last_user_message_at"] = now_ts

    # ✅ FIXED: Only save to Firestore if not called from voice_handlers
    # Voice handler already saved the message with type="voice" and audio_url
    if not skip_firestore_save:
        # Save user's message to Firestore immediately
        current_conversation_id = user_data.get('current_conversation_id')
        was_new_conversation = not current_conversation_id
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
        was_new_conversation = not user_data.get('current_conversation_id')

    current_conversation_id = user_data.get('current_conversation_id')

    # Session-level greeting eligibility for this turn:
    # allowed only for truly new conversation or inactivity >= 12 hours.
    user_data["_greeting_eligible_this_turn"] = bool(
        was_new_conversation
        or (
            inactivity_seconds is not None
            and inactivity_seconds >= GREETING_INACTIVITY_SECONDS
        )
    )
    
    # Get Firestore DB instance for sentiment and takeover checks
    db = get_firestore_db()

    def _build_firestore_user_candidates(canonical_user_id: str, raw_user_id: str) -> list:
        """Build candidate Firestore user IDs to handle legacy/raw identity paths."""
        candidates = []
        for candidate in [canonical_user_id, raw_user_id]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
            if candidate and (
                candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10)
            ):
                alt_candidate = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
                if alt_candidate not in candidates:
                    candidates.append(alt_candidate)
        return candidates

    async def _resolve_conversation_doc_ref(users_coll, conversation_id: str, canonical_user_id: str):
        """
        Resolve conversation doc across canonical/raw/alt user paths.
        Returns (doc_ref, doc_snap, resolved_user_id).
        """
        candidate_user_ids = _build_firestore_user_candidates(canonical_user_id, user_id)
        last_ref = None
        last_snap = None

        for candidate_user_id in candidate_user_ids:
            candidate_ref = users_coll.document(candidate_user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            ).document(conversation_id)
            candidate_snap = await asyncio.to_thread(candidate_ref.get)
            last_ref = candidate_ref
            last_snap = candidate_snap
            if candidate_snap.exists:
                return candidate_ref, candidate_snap, candidate_user_id

        return last_ref, last_snap, canonical_user_id

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
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                app_id_for_firestore = "linas-ai-bot-backend"
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                conv_doc_ref = users_coll.document(canonical_user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
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

                conv_doc_ref, doc_snap, canonical_user_id = await _resolve_conversation_doc_ref(
                    users_coll,
                    current_conversation_id,
                    canonical_user_id,
                )
                if doc_snap.exists:
                    await asyncio.to_thread(conv_doc_ref.update, update_payload)
                    print(f"✅ Conversation marked as waiting_human in Firebase")
                    try:
                        from services.live_chat_service import live_chat_service
                        live_chat_service.invalidate_cache()
                        asyncio.create_task(live_chat_service._refresh_index_for_conversation(canonical_user_id, current_conversation_id))
                    except Exception as idx_err:
                        print(f"⚠️ Index refresh after handover: {idx_err}")
                else:
                    print(f"⚠️ Conversation {current_conversation_id} not found in Firestore (tried canonical + alternate path)")
            except Exception as e:
                print(f"⚠️ Failed to mark conversation as waiting_human: {e}")

        config.user_in_human_takeover_mode[user_id] = True

        escalation_messages = {
            "ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏",
            "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏",
            "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏"
        }
        calm_handover_messages = {
            "ar": "أسف/ة إنك مش راضي/ة، رح حوّلك عند واحد من موظفينا يتواصل معك 🙏",
            "en": "Sorry you're not satisfied. I'll transfer you to one of our staff to connect with you 🙏",
            "fr": "Désolé que vous ne soyez pas satisfait. Je vous transfère à un de nos employés 🙏",
        }
        issues = set(detected_issues or [])
        should_use_calm_handover = bool(
            issues.intersection({"offensive_language", "anger_detected"})
        )
        escalation_msg = escalation_messages.get(user_data.get('user_preferred_lang', 'ar'), escalation_messages['ar'])
        if should_use_calm_handover:
            escalation_msg = calm_handover_messages.get(
                user_data.get('user_preferred_lang', 'ar'),
                calm_handover_messages["ar"],
            )
        await send_message_func(user_id, escalation_msg)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            escalation_msg,
            current_conversation_id,
            user_name,
            user_data.get('phone_number'),
            metadata={"handled_by": "ai", "source": "smart_message", "event": "auto_handover_escalation"},
        )
        # Safety re-assertion: avoid any downstream save path from accidentally
        # reverting the conversation back to bot_active.
        try:
            if current_conversation_id:
                await set_human_takeover_status(user_id, current_conversation_id, True)
        except Exception as takeover_fix_error:
            print(f"⚠️ Failed to re-assert takeover status after escalation save: {takeover_fix_error}")

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

    # AI-primary: GPT decides when to transfer to human (handover_degree, human_handover action).
    # Sentiment is still logged for dashboard; escalation decision is delegated to GPT.
    sentiment_analysis = sentiment_service.analyze_sentiment(
        user_id=user_id,
        message=raw_msg,
        language=user_data.get('user_preferred_lang', 'ar')
    )
    
    # Update conversation sentiment in Firebase (for dashboard/analytics only)
    if db and user_data.get('current_conversation_id'):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
            conv_doc_ref, doc_snap, _ = await _resolve_conversation_doc_ref(
                users_coll,
                user_data['current_conversation_id'],
                canonical_user_id,
            )
            if not doc_snap or not doc_snap.exists:
                raise ValueError("Conversation not found for sentiment update")
            await asyncio.to_thread(conv_doc_ref.update, {
                "sentiment": sentiment_analysis["sentiment"],
                "last_updated": datetime.datetime.now()
            })
            print(f"✅ Updated conversation sentiment to: {sentiment_analysis['sentiment']}")
        except Exception as e:
            print(f"⚠️ Failed to update sentiment in Firebase: {e}")

    # Check Firestore for human takeover status (use canonical path + alternate fallback)
    if db and user_data.get('current_conversation_id'):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
            conv_doc_ref, doc_snap, _ = await _resolve_conversation_doc_ref(
                users_coll,
                user_data['current_conversation_id'],
                canonical_user_id,
            )
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
                                user_name, user_data.get('phone_number'),
                                metadata={"handled_by": "ai", "source": "smart_message", "event": "operator_assigned_notice"},
                            )
                            user_data['notified_human_takeover'] = True
                    else:
                        # User is in waiting queue (no operator yet) — always send "please wait" (every time user speaks)
                        print(f"[handle_message] INFO: User {user_id} in waiting queue. Sending waiting auto-reply.")
                        waiting_msg = get_dynamic_message("waiting_queue_message", user_lang) or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
                        await send_message_func(user_id, waiting_msg)
                        await save_conversation_message_to_firestore(
                            user_id, "ai", waiting_msg, current_conversation_id,
                            user_name, user_data.get('phone_number'),
                            metadata={"handled_by": "ai", "source": "smart_message", "event": "waiting_queue_autoreply"},
                        )
                    return
            else:
                print(f"WARNING: Conversation {user_data['current_conversation_id']} not found in Firestore during takeover check.")
        except Exception as e:
            print(f"❌ ERROR checking human takeover status from Firestore for user {user_id}: {e}")

    ai_primary_mode = bool(getattr(config, "AI_PRIMARY_ORCHESTRATION", True))

    # Greeting policy (code-driven) runs only in non AI-primary mode.
    # In AI-primary mode, greeting timing/wording decisions are delegated to AI.
    if not ai_primary_mode:
        # Greeting policy:
        # - New conversation => send greeting first
        # - Existing conversation but user inactive >= threshold => send greeting first
        greeting_sent_for_conv = user_data.get("greeting_sent_for_conversation_id")
        should_greet_now = False
        if current_conversation_id and greeting_sent_for_conv != current_conversation_id:
            if was_new_conversation:
                should_greet_now = True
            elif inactivity_seconds is not None and inactivity_seconds >= GREETING_INACTIVITY_SECONDS:
                should_greet_now = True

        if should_greet_now:
            user_lang = user_data.get('user_preferred_lang', 'ar')
            greeting_msg = _get_session_greeting_message(user_lang)
            await send_message_func(user_id, greeting_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                greeting_msg,
                current_conversation_id,
                user_name,
                user_data.get('phone_number'),
                metadata={"handled_by": "ai", "source": "session_greeting"},
            )
            user_data["greeting_sent_for_conversation_id"] = current_conversation_id

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
