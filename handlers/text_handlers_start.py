# handlers/text_handlers_start.py
# Handles the /start command for WhatsApp users

from handlers.text_handlers_firestore import *


async def start_command(user_id: str, user_name: str, send_message_func, send_action_func):
    print("DEBUG: 🧩 ENTERED text_handlers_start.start_command")
    """
    Handles the /start command for WhatsApp users.
    Initializes user state and sends a welcome message.
    """
    config.user_names[user_id] = user_name

    # Initialize all user states to ensure correct initial values
    config.user_context[user_id].clear()
    config.gender_attempts[user_id] = 0
    config.user_last_bot_response_time[user_id] = datetime.datetime.now()
    config.user_in_training_mode[user_id] = False
    config.user_photo_analysis_count[user_id] = 0
    config.user_in_human_takeover_mode[user_id] = False

    # Initialize user_data_whatsapp for this user
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {}
    config.user_data_whatsapp[user_id]['user_preferred_lang'] = 'ar'
    config.user_data_whatsapp[user_id]['initial_user_query_to_process'] = None
    config.user_data_whatsapp[user_id]['awaiting_human_handover_confirmation'] = False
    config.user_data_whatsapp[user_id]['current_conversation_id'] = None

    # NOTE: Gender and customer data are now fetched in process_parsed_message
    # BEFORE this function is called, so we don't need to fetch again here.
    # This avoids duplicate API calls.

    # FIX: Check if gender was already set BEFORE potentially resetting it
    # Gender may have been set from API in process_parsed_message
    existing_gender = config.user_gender.get(user_id)
    if existing_gender and existing_gender in ["male", "female"]:
        print(f"✅ Gender already set (preserving): {existing_gender}")
        config.user_greeting_stage[user_id] = 2  # Skip gender question
    else:
        print(f"ℹ️ Gender not found or unknown, will ask user")
        config.user_gender[user_id] = ""  # Only reset if truly not set
        config.user_greeting_stage[user_id] = 1  # Ask for gender

    # Send initial welcome message
    initial_message = config.WELCOME_MESSAGES.get(config.user_data_whatsapp[user_id]['user_preferred_lang'], config.WELCOME_MESSAGES['ar'])
    await send_message_func(user_id, initial_message)

    # DEBUG: Log before saving welcome message
    phone_for_welcome = config.user_data_whatsapp.get(user_id, {}).get("phone_number")
    print(f"\n{'='*60}")
    print(f"🔍 START_COMMAND: About to save WELCOME message")
    print(f"   user_id: {user_id}")
    print(f"   conversation_id: None (will create new)")
    print(f"   phone_number: {phone_for_welcome}")
    print(f"{'='*60}\n")

    # Save the welcome message to Firestore
    await save_conversation_message_to_firestore(
        user_id=user_id,
        role="ai",
        text=initial_message,
        conversation_id=None,
        user_name=user_name,
        phone_number=phone_for_welcome
    )

    # DEBUG: Log the conversation_id that was created
    new_conv_id = config.user_data_whatsapp.get(user_id, {}).get('current_conversation_id')
    print(f"📍 START_COMMAND: After welcome save, conversation_id is: {new_conv_id}")
