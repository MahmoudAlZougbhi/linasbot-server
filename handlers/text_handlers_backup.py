import asyncio
import datetime
import random
from collections import deque # Keep deque for user_context
import re # For regex used in phone number extraction

import config
from utils.utils import (
    detect_language,
    notify_human_on_whatsapp,
    count_tokens,
    save_for_training_conversation_log,
    get_system_instruction,
    # NEW: Import Firestore utility functions
    save_conversation_message_to_firestore,
    update_dashboard_metric_in_firestore,
    set_human_takeover_status,
    get_firestore_db, # To check takeover status directly
    get_conversation_history_from_firestore # NEW: Fetch conversation history
)
from services.gender_recognition_service import get_gender_from_gpt
from services.chat_response_service import get_bot_chat_response
from services.api_integrations import log_report_event, check_customer_gender, get_customer_by_phone, create_customer
from services.sentiment_escalation_service import sentiment_service
# NEW: Import Q&A Database Service for instant responses (USES DATABASE, NOT JSON)
from services.qa_database_service import get_qa_response
# NEW: Import User Persistence Service for gender and language persistence
from services.user_persistence_service import user_persistence

# The training handlers will also need modification,
# so we'll pass required data directly or make them WhatsApp-aware later.
# For now, we'll import them but note they'll need updates.
from handlers.training_handlers import handle_training_input, start_training_mode as original_start_training_mode, exit_training_mode as original_exit_training_mode

# NEW: Dictionary to hold delayed processing tasks for each user
_delayed_processing_tasks = {}

# --- WhatsApp Adapted Start Command (Called from main.py) ---
async def start_command(user_id: str, user_name: str, send_message_func, send_action_func):
    """
    Handles the /start command for WhatsApp users.
    Initializes user state and sends a welcome message.
    """
    config.user_names[user_id] = user_name

    # Initialize all user states to ensure correct initial values
    config.user_context[user_id].clear() # Clear previous conversation context
    config.gender_attempts[user_id] = 0
    config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    config.user_in_training_mode[user_id] = False
    config.user_photo_analysis_count[user_id] = 0
    config.user_gender[user_id] = "" # Reset gender for a new session
    config.user_greeting_stage[user_id] = 1 # Set to stage 1 to trigger initial greet and gender ask logic
    config.user_in_human_takeover_mode[user_id] = False # NEW: Reset takeover mode on start

    # Initialize user_data_whatsapp for this user if it doesn't exist
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {}
    config.user_data_whatsapp[user_id]['user_preferred_lang'] = 'ar' # Default language for a new session
    config.user_data_whatsapp[user_id]['initial_user_query_to_process'] = None # Reset pending query
    config.user_data_whatsapp[user_id]['awaiting_human_handover_confirmation'] = False # State for human handover confirmation
    config.user_data_whatsapp[user_id]['current_conversation_id'] = None # NEW: Initialize current conversation ID

    # NEW: Create a new conversation document in Firestore for this user
    # We will save the first message (welcome message) to this new conversation.
    # The conversation ID will be stored in user_data_whatsapp.
    # The actual saving of the welcome message will happen after it's sent.

    # NEW: Use persistence service to fetch gender from API
    try:
        api_gender = await user_persistence.get_user_gender(user_id, phone=user_id)
        if api_gender in ["male", "female"]:
            config.user_gender[user_id] = api_gender
            print(f"✅ User {user_id} gender fetched from API on start: {api_gender}")
            log_report_event("gender_updated_from_api", user_name, api_gender, {"method": "API Lookup on Start", "whatsapp_id": user_id})
            config.user_greeting_stage[user_id] = 2 # If gender is known from API, skip asking
        else:
            print(f"ℹ️ User {user_id} gender not found in API on start")
    except Exception as e:
        print(f"❌ ERROR: API lookup for gender on start failed for user {user_id}: {e}")

    # Send initial welcome message
    initial_message = config.WELCOME_MESSAGES.get(config.user_data_whatsapp[user_id]['user_preferred_lang'], config.WELCOME_MESSAGES['ar'])
    await send_message_func(user_id, initial_message)

    # NEW: Save the welcome message to Firestore as the first message in a new conversation
    await save_conversation_message_to_firestore(
        user_id=user_id,
        role="ai", # Bot's welcome message
        text=initial_message,
        conversation_id=None, # Will create a new conversation and store its ID
        user_name=user_name,
        phone_number=None  # No phone number for start command
    )
    # The save_conversation_message_to_firestore function will populate config.user_data_whatsapp[user_id]['current_conversation_id']


# --- WhatsApp Adapted Message Handler (Called from main.py) ---
async def handle_message(user_id: str, user_name: str, user_input_text: str, user_data: dict, send_message_func, send_action_func):
    """
    Main message handler for WhatsApp text messages.
    Combines rapid messages and then processes them.
    """
    config.user_names[user_id] = user_name # Ensure name is always updated
    
    # Ensure defaultdicts are initialized for this user, even if not done in main.py for some reason
    if user_id not in config.user_context:
        config.user_context[user_id] = deque(maxlen=config.MAX_CONTEXT_MESSAGES)
    if user_id not in config.user_pending_messages:
        config.user_pending_messages[user_id] = deque()
    if user_id not in config.user_last_bot_response_time:
        config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    if user_id not in config.user_greeting_stage:
        config.user_greeting_stage[user_id] = 0
    if user_id not in config.user_gender:
        config.user_gender[user_id] = ""
    if user_id not in config.gender_attempts:
        config.gender_attempts[user_id] = 0
    if user_id not in config.user_in_training_mode:
        config.user_in_training_mode[user_id] = False
    if user_id not in config.user_photo_analysis_count:
        config.user_photo_analysis_count[user_id] = 0
    if user_id not in config.user_in_human_takeover_mode: # NEW: Ensure takeover mode is initialized
        config.user_in_human_takeover_mode[user_id] = False
    
    # user_data (from config.user_data_whatsapp[user_id]) will contain:
    # 'user_preferred_lang', 'initial_user_query_to_process', 'awaiting_human_handover_confirmation', 'current_conversation_id'


    if config.user_in_training_mode.get(user_id, False):
        print(f"[handle_message] INFO: User {user_id} in training mode. Handing over to handle_training_input.")
        # Pass necessary data directly to handle_training_input
        await handle_training_input(
            user_id=user_id,
            user_input_text=user_input_text,
            user_data=user_data, # Pass the user_data dict
            send_message_func=send_message_func,
            send_action_func=send_action_func
        )
        return

    raw_msg = user_input_text.strip()

    if not raw_msg:
        print(f"[handle_message] ERROR: No usable text in message for user {user_id}. raw_msg is empty. Exiting.")
        return

    # NEW: Save user's message to Firestore immediately
    current_conversation_id = user_data.get('current_conversation_id')
    await save_conversation_message_to_firestore(user_id, "user", raw_msg, current_conversation_id, user_name, user_data.get('phone_number'))
    # If current_conversation_id was None, save_conversation_message_to_firestore would have created it
    # and updated user_data['current_conversation_id']
    user_data['current_conversation_id'] = config.user_data_whatsapp[user_id]['current_conversation_id'] # Ensure it's updated locally
    
    # Get Firestore DB instance for sentiment and takeover checks
    db = get_firestore_db()
    
    # NEW: Analyze sentiment and check if auto-escalation is needed
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
        
        # Set conversation to waiting for human
        if db and user_data.get('current_conversation_id'):
            try:
                conv_doc_ref.update({
                    "status": "waiting_human",
                    "human_takeover_active": True,  # Mark as needing human intervention
                    "human_takeover_requested": True,
                    "operator_id": None,  # No operator assigned yet
                    "escalation_reason": sentiment_analysis['escalation_reason'],
                    "escalation_score": sentiment_analysis['escalation_score'],
                    "escalation_time": datetime.datetime.now()
                })
                print(f"✅ Conversation marked as waiting_human in Firebase")
                
                # Update in-memory state to prevent bot from responding
                config.user_in_human_takeover_mode[user_id] = True
                
            except Exception as e:
                print(f"⚠️ Failed to mark conversation as waiting_human: {e}")
        
        # Send notification to customer
        escalation_messages = {
            "ar": "شكراً لصبرك. لاحظنا أنك قد تحتاج مساعدة إضافية. سيتم تحويلك إلى أحد موظفينا قريباً. 🙏",
            "en": "Thank you for your patience. We noticed you may need additional help. You'll be transferred to one of our staff members shortly. 🙏",
            "fr": "Merci pour votre patience. Nous avons remarqué que vous pourriez avoir besoin d'aide supplémentaire. Vous serez transféré à l'un de nos employés sous peu. 🙏"
        }
        
        escalation_msg = escalation_messages.get(user_data.get('user_preferred_lang', 'ar'), escalation_messages['ar'])
        await send_message_func(user_id, escalation_msg)
        await save_conversation_message_to_firestore(user_id, "ai", escalation_msg, current_conversation_id, user_name, user_data.get('phone_number'))
        
        # Notify human operators
        notify_human_on_whatsapp(
            user_name, 
            config.user_gender.get(user_id, "unknown"), 
            raw_msg, 
            type_of_notification=f"تصعيد تلقائي - {sentiment_analysis['escalation_reason']}"
        )
        
        # Log the escalation
        log_report_event("auto_escalation", user_name, config.user_gender.get(user_id, "unknown"), {
            "message": raw_msg,
            "reason": sentiment_analysis['escalation_reason'],
            "score": sentiment_analysis['escalation_score'],
            "issues": sentiment_analysis['detected_issues']
        })
        
        # Update metrics
        await update_dashboard_metric_in_firestore(user_id, "auto_escalations", 1)
        
        # Don't process with AI - wait for human
        return

    # NEW: Check Firestore for human takeover status for this conversation
    if db and user_data.get('current_conversation_id'):
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(user_data['current_conversation_id'])
            doc_snap = conv_doc_ref.get()  # Firebase Admin SDK get() is synchronous, not async
            if doc_snap.exists:
                config.user_in_human_takeover_mode[user_id] = doc_snap.to_dict().get('human_takeover_active', False)
                if config.user_in_human_takeover_mode[user_id]:
                    print(f"[handle_message] INFO: User {user_id} conversation {user_data['current_conversation_id']} is in human takeover mode. AI will not respond.")
                    # Optionally, send a message indicating human is taking over, but only once
                    if not user_data.get('notified_human_takeover'):
                        await send_message_func(user_id, "ملاحظة: تم تحويل هذه المحادثة إلى موظف بشري. سيقوم فريقنا بالرد عليك قريباً.")
                        user_data['notified_human_takeover'] = True
                    return # Exit without AI processing if in takeover mode
            else:
                print(f"WARNING: Conversation {user_data['current_conversation_id']} not found in Firestore during takeover check.")
        except Exception as e:
            print(f"❌ ERROR checking human takeover status from Firestore for user {user_id}: {e}")
            # Continue processing with AI if Firestore check fails

    # NEW: Check if it's the very first message after start, and if gender is still unknown
    if config.user_greeting_stage[user_id] == 1 and not config.user_gender.get(user_id):
        common_greetings_only = ["hi", "hello", "مرحبا", "سلام", "اهلين", "صباح الخير", "مساء الخير", "كيفك", "كيف الحال", "kifak", "shu", "bonjour", "salut"]
        is_only_greeting = any(g == raw_msg.lower().strip() for g in common_greetings_only)

        if not is_only_greeting:
            if user_data['initial_user_query_to_process'] is None:
                user_data['initial_user_query_to_process'] = raw_msg
        else:
            user_data['initial_user_query_to_process'] = None


    # NEW: Language locking - only detect on first message, then lock it
    if not user_data.get('language_locked', False):
        # First message - detect and LOCK language
        lang_result = detect_language(raw_msg)
        current_message_lang = lang_result['language']
        user_data['user_preferred_lang'] = current_message_lang
        user_data['language_confidence'] = lang_result['confidence']
        user_data['language_locked'] = True  # Lock the language
        user_persistence.save_user_language(user_id, current_message_lang)  # NOT async - no await
        print(f"[handle_message] 🔒 Language LOCKED for user {user_id}: {current_message_lang} (confidence: {lang_result['confidence']:.2%})")
    else:
        # Language already locked - don't change it
        print(f"[handle_message] ℹ️ Language already locked for user {user_id}: {user_data.get('user_preferred_lang')}")

    # --- NEW MESSAGE COMBINING LOGIC ---
    config.user_pending_messages[user_id].append(raw_msg)

    # Cancel any previously scheduled processing task for this user
    if user_id in _delayed_processing_tasks and not _delayed_processing_tasks[user_id].done():
        _delayed_processing_tasks[user_id].cancel()

    # Schedule a new processing task
    _delayed_processing_tasks[user_id] = asyncio.create_task(
        _delayed_process_messages(user_id, user_data, send_message_func, send_action_func)
    )

    # No return needed here, the async task will handle the actual response


async def _delayed_process_messages(user_id: str, user_data: dict, send_message_func, send_action_func):
    try:
        await send_action_func(user_id) # Send typing indicator
        await asyncio.sleep(config.MESSAGE_COMBINING_DELAY)

        if config.user_pending_messages[user_id]:
            combined_message = " ".join(config.user_pending_messages[user_id])
            config.user_pending_messages[user_id].clear() # Clear queue after combining

            await _process_and_respond(user_id, user_name=config.user_names.get(user_id, "عميل"),
                                       user_input_to_process=combined_message,
                                       user_data=user_data, # Pass the user_data dict
                                       send_message_func=send_message_func,
                                       send_action_func=send_action_func)
            config.user_last_bot_response_time[user_id] = datetime.datetime.now()
        else:
            pass  # Queue was empty

    except asyncio.CancelledError:
        pass  # Task was cancelled
    except Exception as e:
        print(f"[_delayed_process_messages] ERROR: An error occurred in delayed processing for user {user_id}: {e}")
        import traceback
        traceback.print_exc()

async def _process_and_respond(user_id: str, user_name: str, user_input_to_process: str, user_data: dict, send_message_func, send_action_func):
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    current_gender = config.user_gender.get(user_id, "unknown")
    current_preferred_lang = user_data.get('user_preferred_lang', 'ar')
    current_conversation_id = user_data.get('current_conversation_id') # NEW: Get conversation ID


    # NEW: Check if human takeover is active for this conversation
    if config.user_in_human_takeover_mode.get(user_id, False):
        print(f"[_process_and_respond] INFO: Conversation {current_conversation_id} for user {user_id} is in human takeover mode. AI will not respond.")
        # No AI response, but we still need to log the user's message to Firestore (done in handle_message)
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
            # NEW: Update metric for human handover
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        elif any(kw in user_input_lower for kw in rejection_keywords_ar):
            gpt_response_data = {
                "action": "return_to_normal_chat",
                "bot_reply": "تمام، كيف بقدر أساعدك الآن؟",
                "detected_language": current_preferred_lang,
                "detected_gender": current_gender if current_gender != "unknown" else None,
                "current_gender_from_config": current_gender
            }
            user_data['awaiting_human_handover_confirmation'] = False
        else:
            # Fetch conversation history from Firestore
            conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)
            gpt_response_data = await get_bot_chat_response(
                user_id=user_id,
                user_input=user_input_to_process,
                current_context_messages=conversation_history,
                current_gender=current_gender,
                current_preferred_lang=current_preferred_lang,
                is_initial_message_after_start=is_initial_message_for_gpt,
                initial_user_query_to_process=initial_user_query_to_process_original
            )

    else: # Normal processing if not awaiting confirmation
        query_to_send_to_gpt = user_input_to_process

        if current_gender in ["male", "female"] and config.user_greeting_stage[user_id] == 1 and initial_user_query_to_process_original:
            user_data['initial_user_query_to_process'] = None
            query_to_send_to_gpt = initial_user_query_to_process_original
            config.user_greeting_stage[user_id] = 2
            is_initial_message_for_gpt = False

            gender_acknowledgement = "أهلاً بك أستاذ " if current_gender == "male" else "أهلاً بكِ سيدتي "
            await send_message_func(user_id, f"{gender_acknowledgement}{user_name}! شكراً لتحديد جنسك. سأجيب على استفسارك الأصلي.")
            # NEW: Save gender acknowledgement message to Firestore
            await save_conversation_message_to_firestore(user_id, "ai", f"{gender_acknowledgement}{user_name}! شكراً لتحديد جنسك. سأجيب على استفسارك الأصلي.", current_conversation_id, user_name, user_data.get('phone_number'))

        # ✨ NEW: Check Q&A Database BEFORE calling GPT-4 (saves AI cost & time!)
        print(f"[_process_and_respond] 🔍 Checking Q&A database for: '{query_to_send_to_gpt}'")
        qa_response = await get_qa_response(query_to_send_to_gpt, current_preferred_lang)
        
        if qa_response:
            # ✅ Found match in Q&A database! Use it directly
            print(f"[_process_and_respond] ✅ Q&A MATCH FOUND! Using instant response (no GPT-4 call)")
            print(f"[_process_and_respond] ��� AI Cost Saved: ~$0.02-0.05")
            print(f"[_process_and_respond] ⚡ Response Time: <50ms (vs 2-5s with GPT-4)")
            
            # Send Q&A response to user
            await send_message_func(user_id, qa_response)
            
            # Save to Firestore with special metadata
            await save_conversation_message_to_firestore(
                user_id, "ai", qa_response, 
                current_conversation_id, user_name, 
                user_data.get('phone_number'),
                metadata={
                    "source": "qa_database",
                    "ai_cost_saved": True,
                    "response_type": "instant"
                }
            )
            
            # Update metrics
            await update_dashboard_metric_in_firestore(user_id, "qa_responses_used", 1)
            
            # Set greeting stage to 2 (normal conversation)
            config.user_greeting_stage[user_id] = 2
            
            # Log for training
            save_for_training_conversation_log(query_to_send_to_gpt, qa_response)
            
            return  # Exit early - no need for GPT-4!
        
        # No Q&A match found, proceed with GPT-4
        print(f"[_process_and_respond] ℹ️ No Q&A match found. Proceeding with GPT-4...")
        
        # Fetch conversation history from Firestore
        conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)
        
        gpt_response_data = await get_bot_chat_response(
            user_id=user_id,
            user_input=query_to_send_to_gpt,
            current_context_messages=conversation_history,
            current_gender=current_gender,
            current_preferred_lang=current_preferred_lang,
            is_initial_message_after_start=is_initial_message_for_gpt,
            initial_user_query_to_process=None
        )

    action = gpt_response_data.get("action")
    bot_reply_text = gpt_response_data.get("bot_reply")
    detected_gender_from_gpt = gpt_response_data.get("detected_gender")
    detected_language = gpt_response_data.get("detected_language")


    if detected_language and user_data.get('user_preferred_lang') != detected_language:
        user_data['user_preferred_lang'] = detected_language

    if detected_gender_from_gpt and config.user_gender.get(user_id) != detected_gender_from_gpt:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "User Input Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        # NEW: Save gender to API for persistence
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=user_name)
    elif detected_gender_from_gpt and config.user_gender.get(user_id) == "unknown" and detected_gender_from_gpt in ["male", "female"]:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "GPT Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        # NEW: Save gender to API for persistence
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=user_name)

    # Process the action requested by GPT
    if action in ["initial_greet_and_ask_gender", "ask_gender"]:
        if current_gender in ["male", "female"]:
            await send_message_func(user_id, bot_reply_text)
            await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save overridden reply
        else:
            config.gender_attempts[user_id] += 1
            if config.gender_attempts[user_id] >= config.MAX_GENDER_ASK_ATTEMPTS:
                fallback_reply = "عذراً، لم أتمكن من تحديد جنسك بشكل دقيق. لتقديم أفضل مساعدة، قد تحتاج للتواصل مع فريقنا مباشرة. أو يمكنك المحاولة مجدداً بعبارة واضحة كـ 'أنا شب' أو 'أنا صبية'."
                await send_message_func(user_id, fallback_reply)
                await save_conversation_message_to_firestore(user_id, "ai", fallback_reply, current_conversation_id, user_name, user_data.get('phone_number')) # Save fallback reply
                config.user_greeting_stage[user_id] = 2
            else:
                await send_message_func(user_id, bot_reply_text)
                await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply

    elif action == "confirm_gender":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        config.user_greeting_stage[user_id] = 2

    elif action == "confirm_booking_details":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        config.user_greeting_stage[user_id] = 2

    elif action == "human_handover_initial_ask":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        user_data['awaiting_human_handover_confirmation'] = True

    elif action == "human_handover_confirmed":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        # WHATSAPP_TO is a single number in config.py, so no need for update.effective_user.first_name, etc.
        notify_human_on_whatsapp(user_name, current_gender, user_input_to_process, type_of_notification="طلب محادثة مع موظف (مؤكد)")
        log_report_event("human_handover", user_name, current_gender, {"message": user_input_to_process, "status": "confirmed"})
        # Metric update is already handled above when confirmation keywords are detected.

    elif action == "return_to_normal_chat":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply

    elif action == "human_handover":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        notify_human_on_whatsapp(user_name, current_gender, user_input_to_process, type_of_notification="طلب محادثة مع موظف (مباشر)")
        log_report_event("human_handover", user_name, current_gender, {"message": user_input_to_process, "status": "direct"})
        # NEW: Update metric for human handover (direct request)
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)

    elif action in ["answer_question", "normal_chat", "unknown_query", "provide_info", "tool_call", "ask_for_details_for_booking", "ask_for_service_type", "ask_for_details", "ask_for_tattoo_photo", "check_customer_status"]:
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number')) # Save bot reply
        config.user_greeting_stage[user_id] = 2

    else:
        await send_message_func(user_id, "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى.")
        await save_conversation_message_to_firestore(user_id, "ai", "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى.", current_conversation_id, user_name, user_data.get('phone_number')) # Save fallback reply
        print(f"[_process_and_respond] ERROR: User {user_id} received fallback reply due to unexpected action: {action}")

    # No longer adding to config.user_context here, as Firestore is the source of truth.
    # The context for GPT will be built from Firestore in chat_response_service.py.

    if user_input_to_process.strip() and not user_input_to_process.lower().startswith('/start'):
        # For token counting, we only need the user input and bot reply,
        # and the system instruction. user_id and current_preferred_lang are needed for get_system_instruction.
        prompt_tokens = count_tokens(get_system_instruction(user_id, current_preferred_lang) + "\n\n" + user_input_to_process)
        completion_tokens = count_tokens(bot_reply_text)
        total_tokens = prompt_tokens + completion_tokens
        # Assuming OpenAI pricing: GPT-4o input $5/M tokens, output $15/M tokens
        cost = (prompt_tokens / 1_000_000 * 5) + (completion_tokens / 1_000_000 * 15)
        print(f"[_process_and_respond] 🔹 Prompt tokens: {prompt_tokens}")
        print(f"[_process_and_respond] 🔹 Completion tokens: {completion_tokens}")
        print(f"[_process_and_respond] 📊 Total tokens: {total_tokens} | 💰 Estimated cost: ${cost:.6f}\n")
        save_for_training_conversation_log(user_input_to_process, bot_reply_text)

    config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    return
