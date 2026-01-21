# services/chat_response_service.py
import json
import random
import config
from utils.utils import detect_language, get_system_instruction, get_openai_tools_schema
from services.llm_core_service import client
from services.gender_recognition_service import get_gender_from_gpt
from services.moderation_service import moderate_content, check_rate_limits, get_safe_response_for_violation, get_rate_limit_response
from difflib import SequenceMatcher
import datetime
import re

# Import all API functions from api_integrations
from services import api_integrations

# Import local Q&A service for context injection
from services.local_qa_service import local_qa_service

# Import dynamic model selector for cost optimization
from services.dynamic_model_selector import select_optimal_model

# Lebanon timezone - imported once at module level for performance
try:
    from zoneinfo import ZoneInfo
    LEBANON_TZ = ZoneInfo("Asia/Beirut")
except ImportError:
    import pytz
    LEBANON_TZ = pytz.timezone("Asia/Beirut")

_custom_qa_cache = {}


def format_qa_for_context(qa_pairs: list) -> str:
    """
    Format Q&A pairs for injection into GPT system prompt.

    Args:
        qa_pairs: List of dicts with question, answer, similarity

    Returns:
        Formatted string for system prompt
    """
    if not qa_pairs:
        return ""

    formatted_lines = []
    for i, qa in enumerate(qa_pairs, 1):
        similarity_pct = qa.get("similarity", 0) * 100
        formatted_lines.append(
            f"---\n"
            f"**Trained Q{i}** (Match: {similarity_pct:.0f}%)\n"
            f"Question: {qa.get('question', '')}\n"
            f"Answer: {qa.get('answer', '')}\n"
        )

    return "\n".join(formatted_lines)

def validate_language_match(user_language: str, bot_response: str, detected_response_lang: str) -> tuple:
    """
    Validate bot response matches user language
    Returns: (is_valid: bool, error_message: str)
    """
    # Character patterns for each language
    patterns = {
        'ar': r'[\u0600-\u06FF]',  # Arabic
        'en': r'[a-zA-Z]',
        'fr': r'[a-zA-Z]'
    }

    # Franco should get Arabic response
    if user_language == 'franco':
        user_language = 'ar'

    if user_language not in patterns:
        return True, ""  # Skip validation for unknown languages

    # Count characters matching expected language
    expected_chars = len(re.findall(patterns[user_language], bot_response))
    total_chars = len(re.sub(r'\s', '', bot_response))  # Exclude spaces

    if total_chars == 0:
        return True, ""

    match_ratio = expected_chars / total_chars

    if match_ratio < 0.7:  # 70% threshold
        return False, f"Language mismatch: {match_ratio:.1%} match (expected ≥70% {user_language})"

    return True, ""

# user_id is the WhatsApp phone number
async def get_bot_chat_response(user_id: str, user_input: str, current_context_messages: list, current_gender: str, current_preferred_lang: str, response_language: str, is_initial_message_after_start: bool, initial_user_query_to_process: str = None) -> dict:
    user_name = config.user_names.get(user_id, "client") 
    current_gender_attempts = config.gender_attempts.get(user_id, 0)
    
    # Extract customer phone number (without country code for API calls)
    customer_phone_full = config.user_data_whatsapp.get(user_id, {}).get('phone_number')
    customer_phone_clean = None
    if customer_phone_full:
        customer_phone_clean = str(customer_phone_full).replace("+", "").replace(" ", "").replace("-", "")
        if customer_phone_clean.startswith("961"):
            customer_phone_clean = customer_phone_clean[3:]  # Remove Lebanon country code
    
    # Extract first name only for natural conversation
    customer_first_name = None
    if user_name and user_name != "client":
        customer_first_name = user_name.split()[0]  # "Nour Jaffala" -> "Nour"
    
    # Check rate limits first
    within_limits, limit_message = await check_rate_limits(user_id, 'message')
    if not within_limits:
        return {
            "action": "rate_limit_exceeded",
            "bot_reply": get_rate_limit_response(current_preferred_lang, limit_message),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender
        }
    
    # Moderate content for policy violations
    is_safe, moderation_result = await moderate_content(user_input, user_id)
    if not is_safe:
        print(f"âڑ ï¸ڈ Content flagged for user {user_id}: {moderation_result}")
        return {
            "action": "content_moderated",
            "bot_reply": get_safe_response_for_violation(current_preferred_lang),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender
        }
    
    explicitly_detected_gender_from_input = None
    if user_input.strip():
        explicitly_detected_gender_from_input = await get_gender_from_gpt(user_input)
        print(f"DEBUG GPT Gender Recognition: Input '{user_input}' -> Detected as '{explicitly_detected_gender_from_input}' (for logging/debug, GPT will decide action)")

    # NOTE: conversation_log.jsonl is NO LONGER USED
    # Q&A matching is now handled by qa_database_service.py (API-based)
    # This happens in text_handlers.py BEFORE calling this function
    # If we reach here, it means no Q&A match was found, so proceed with GPT-4

    # NEW: Get relevant Q&A pairs to inject into GPT context
    # This ensures GPT knows about trained answers even for partial matches
    relevant_qa = await local_qa_service.get_relevant_qa_pairs(
        question=user_input,
        language=current_preferred_lang,
        limit=3
    )
    qa_reference_text = format_qa_for_context(relevant_qa)

    if relevant_qa:
        print(f"📚 Injecting {len(relevant_qa)} Q&A pairs into GPT context")
        for qa in relevant_qa:
            print(f"   - Q: '{qa['question'][:50]}...' (Match: {qa['similarity']:.0%})")

    # Get the core system instruction from utils.py, which now contains the JSON output format requirement.
    # Pass the current_gender and Q&A reference to get_system_instruction
    system_instruction_core = get_system_instruction(user_id, current_preferred_lang, qa_reference_text)

    # Log which training files GPT is receiving
    print(f"📄 GPT will receive knowledge_base.txt in context")
    print(f"📄 GPT will receive style_guide.txt in context")

    # Detect if this is a price-related question
    price_keywords = [
        'price', 'cost', 'how much', 'pricing', 'سعر', 'اسعار', 'كم', 'قديش', 'أديش', 'تكلفة',
        'prix', 'coût', 'combien', 'tarif', 'adesh', 'adde', '2adde', '2adesh', 'kam', 'sa3er'
    ]
    user_input_lower = user_input.lower()
    is_price_question = any(keyword in user_input_lower for keyword in price_keywords)

    if is_price_question:
        print(f"📄 GPT will receive price_list.txt in context (price-related question detected)")

    # Build name instruction based on whether name is known
    name_is_known = user_name and user_name != "client"
    early_name_instruction = (
        "**Early Name Capture (CRITICAL FOR NEW USERS):**\n"
        f"**CURRENT NAME STATUS: {'KNOWN - ' + user_name if name_is_known else 'NOT KNOWN'}**\n\n"
        + (
            f"The user's name is already known as '{user_name}'. Do NOT ask for their name again.\n"
            if name_is_known else
            "**🚨 NAME IS NOT KNOWN - YOU MUST ASK FOR IT! 🚨**\n"
            "IMMEDIATELY after the user confirms their gender (says 'male', 'female', 'شاب', 'صبية', etc.), "
            "your VERY NEXT response MUST ask for their full name. Do NOT skip this step!\n"
            "Ask politely: 'May I have your full name please?' / 'ممكن اسمك الكامل من فضلك؟'\n"
            "Do NOT proceed to ask about services, body areas, or booking until you have their name.\n"
            "The flow for new users is: 1) Gender → 2) Full Name → 3) Service/Booking questions.\n"
        )
    )

    # Get current Lebanon time for GPT to use in date/time calculations
    current_lebanon_time = datetime.datetime.now(LEBANON_TZ)
    current_date_str = current_lebanon_time.strftime("%Y-%m-%d")
    current_time_str = current_lebanon_time.strftime("%H:%M:%S")
    current_day_name = current_lebanon_time.strftime("%A")

    # Build gender instruction based on whether gender is already known
    gender_info_line = f"- **Gender**: Current gender is '{current_gender}'. "
    if current_gender in ['male', 'female']:
        gender_info_line += f"**GENDER IS ALREADY '{current_gender.upper()}' - NEVER ASK FOR GENDER! Just use '{current_gender}' for pricing and services. DO NOT say 'to give you personalized pricing, are you male or female?' - you already know!**\n"
    else:
        gender_info_line += "Only ask if it's 'unknown' AND you need it for the service.\n"

    # Enhanced booking instruction: GPT is responsible for parsing date/time from natural language
    booking_instruction = (
        "**BOOKING FLOW - FOLLOW THIS EXACT ORDER:**\n\n"
        "**STEP 1: CHECK IF NEW OR EXISTING CUSTOMER**\n"
        "When user wants to book:\n"
        f"- Call `check_next_appointment(phone='{customer_phone_clean}')` to check for existing appointments\n"
        "- **CRITICAL: If the response says 'Customer not found' or success=false → This is a NEW customer!**\n"
        "- For NEW customers: Skip to STEP 3 immediately. Do NOT stop or show an error!\n"
        "- For EXISTING customers with appointments: Go to STEP 2\n\n"
        "**STEP 2: HANDLE EXISTING APPOINTMENT (only if found)**\n"
        "If the tool returns an existing appointment (success=true with appointment data), ask:\n"
        "'I see you already have an appointment for [service] on [date] at [time]. Would you like to:'\n"
        "'1. Keep this appointment and add a NEW one'\n"
        "'2. Change/reschedule this existing appointment'\n"
        "Wait for their choice before proceeding.\n\n"
        "**STEP 3: COLLECT ALL REQUIRED BOOKING DETAILS**\n"
        "Before calling `create_appointment`, you MUST have ALL of these:\n"
        "1. Service type (hair removal, tattoo removal, CO2, whitening, etc.)\n"
        "2. **BODY PART (MANDATORY for hair removal & tattoo removal)** - Ask 'Which area would you like to treat?'\n"
        "3. Machine preference (Neo, Quadro, Trio for hair removal; Pico for tattoo)\n"
        "4. **BRANCH (MANDATORY)** - You MUST ask which branch. Options: Beirut (Manara) or Antelias (Center Haj). NEVER assume a branch!\n"
        "5. Date and time\n\n"
        "**🚨 BODY PART REQUIREMENT:**\n"
        "- For Laser Hair Removal (service_id 1 or 12): body_part_ids is REQUIRED\n"
        "- For Tattoo Removal (service_id 13): body_part_ids is REQUIRED\n"
        "- NEVER call `create_appointment` for these services without body_part_ids!\n"
        "- If body part is missing, ask: 'Which area would you like the treatment on?'\n\n"
        "**Appointment Booking Process:**\n"
        "When the user expresses intent to book an appointment, you are responsible for gathering *all* necessary details for the `create_appointment` tool. These details are: Full Name, Specific Service, **Body Area(s) (REQUIRED for laser hair removal and tattoo removal)**, Preferred Machine (Neo, Quadro, or Trio), Preferred Branch, and an Exact Date and Time.\n"
        "**IMPORTANT - Information Already Known:**\n"
        f"- **Customer Name**: {('The customer full name is ' + user_name + '. Their first name is ' + str(customer_first_name) + '. You already know their name, so DO NOT ask for it again. Use ' + str(customer_first_name) + ' when addressing them.') if name_is_known else '**NAME IS NOT KNOWN YET.** You MUST ask for their full name before proceeding with booking. Ask: May I have your full name please? / ممكن اسمك الكامل؟'}\n"
        f"- **Customer Phone**: The customer's phone number (without country code) is '{customer_phone_clean}'. When using tools like check_next_appointment, update_appointment_date, or create_appointment that require a phone parameter, ALWAYS use '{customer_phone_clean}'. DO NOT ask for phone number, DO NOT extract it from conversation.\n"
        f"{gender_info_line}"
        "**Appointment Management:**\n"
        "- To CHECK appointments: Use `check_next_appointment` tool with phone='{customer_phone_clean}'\n"
        "- To CREATE new appointment: Use `create_appointment` tool\n"
        "- To RESCHEDULE/UPDATE appointment (2-step process):\n"
        "  STEP 1 - When customer asks to change/reschedule:\n"
        "    1. Call `check_next_appointment(phone='{customer_phone_clean}')` to get current appointment details and appointment_id\n"
        "    2. Ask customer to CONFIRM the change with a clear message showing OLD time vs NEW time\n"
        "    3. Set action='confirm_appointment_reschedule'\n"
        "    Example: 'I see your appointment is on Nov 16 at 10:00 AM. You want to change it to 11:00 AM on the same day, correct?'\n"
        "  STEP 2 - When customer confirms (says 'yes', 'correct', 'confirm', etc.) AND you just asked for confirmation:\n"
        "    1. Call `check_next_appointment(phone='{customer_phone_clean}')` FIRST to get current appointment details\n"
        "    2. Call `update_appointment_date(appointment_id=0, phone='{customer_phone_clean}', date='YYYY-MM-DD HH:MM:SS')` with appointment_id=0 (placeholder)\n"
        "    3. The system will AUTO-CHAIN the correct appointment_id from check_next_appointment's response\n"
        "    4. After tools execute, confirm the update to customer\n"
        "  IMPORTANT: Call BOTH tools together - the system handles getting the correct appointment_id automatically.\n"
        "- To CANCEL appointment: No API available - offer human handover\n"
        "**What You MUST Ask For (New Appointments):**\n"
        "1. Service/treatment they want (if not clear)\n"
        "2. Body area (for laser hair removal)\n"
        "3. Preferred machine (Neo, Quadro, or Trio) - or use default\n"
        "4. **Preferred branch - MUST ASK, NEVER ASSUME!** Options: Beirut (Manara) or Antelias (Center Haj)\n"
        "5. Date and time\n"
        f"**🕐 CURRENT DATE AND TIME (Lebanon/Beirut): {current_day_name}, {current_date_str} at {current_time_str}**\n"
        "**Date and Time Conversion (CRITICAL):** You MUST intelligently convert any natural language date/time expressions (e.g., 'tomorrow at 3 PM', 'next Friday', 'in 3 days', 'tonight at 7:30 PM') into the exact 'YYYY-MM-DD HH:MM:SS' format. "
        f"Use the CURRENT DATE AND TIME shown above ({current_date_str} {current_time_str}) as your reference point for 'today', 'tomorrow', 'next week', etc. "
        "The appointment date must be in the future (after the current time shown above) and not more than 365 days from today. If the user provides only a day (e.g., 'tomorrow'), suggest a default time like '10:00:00' or '14:00:00 (2 PM)'. If only a time is given (e.g., 'at 3 PM'), check if that time is AFTER the current time - if yes, use today's date; if no, use tomorrow's date. You must confirm the extracted date and time in your `bot_reply` before trying to book.\n"
        "**Confirmation and Tool Call:** Do NOT call `create_appointment` until you have *all* required parameters and you have *confirmed them with the user* in your `bot_reply`. If details are missing, your `action` should be `ask_for_details_for_booking`, and your `bot_reply` should ask for the *next specific missing piece of information*. For example, 'طھظ…ط§ظ…طŒ ظˆط£ظٹ ط¬ظ‡ط§ط² ط¨طھظپط¶ظ„طں' or 'ظˆظ…ط§ ظ‡ظˆ ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„طں' (NOT phone or gender if already known). If the user says 'ok book it' but not all info is there, you still ask for the missing parts.\n"
        "**Example of Confirmation:** If user says 'ok book me for tomorrow 1pm', and you know all other details, your `bot_reply` should be: 'طھظ…ط§ظ…طŒ ط¥ط°ط§ظ‹ ظ…ظˆط¹ط¯ظƒ ط¨ظƒط±ط§ ط§ظ„ط³ط¨طھ 28 طھظ…ظˆط² ط§ظ„ط³ط§ط¹ط© 1:00 ط¨ط¹ط¯ ط§ظ„ط¸ظ‡ط± ظپظٹ ظپط±ط¹ ط§ظ„ظ…ظ†ط§ط±ط© ط¹ظ„ظ‰ ط¬ظ‡ط§ط² ط§ظ„ظ†ظٹظˆطŒ طµط­ظٹط­طں' and `action` should be `confirm_booking_details`. Only call the tool (`create_appointment`) after final confirmation by the user (e.g., 'yes', 'ok', 'confirm'). If you have all information and user confirms, then `action` should be `tool_call` and `bot_reply` should inform the user that you are booking.\n"
        "**🚨 AFTER SUCCESSFUL BOOKING - Confirmation Message MUST Include:**\n"
        "When the appointment is successfully created, your confirmation message MUST mention ALL of these details:\n"
        "1. Date and time of the appointment\n"
        "2. **Body part/area being treated** (e.g., 'Full Arms', 'Legs', 'Back') - ALWAYS include this!\n"
        "3. Machine being used (Neo, Quadro, Trio, etc.)\n"
        "4. Branch location\n"
        "5. Price (if available in the API response)\n"
        "Example: 'Your appointment for laser hair removal on your **legs** has been booked for tomorrow at 12:00 PM with the Neo machine at our Beirut branch. The session costs $80.'"
    )

    # Enhanced gender ask instruction: GPT is responsible for when and how to ask
    # Language map for gender questions
    language_map_gender = {
        "ar": "Arabic",
        "en": "English",
        "fr": "French",
        "franco": "Lebanese Arabic in Arabic script (NOT Latin characters)"
    }
    target_lang_gender = language_map_gender.get(current_preferred_lang, current_preferred_lang)

    # Build conditional warning for when gender is already known
    gender_known_warning = f"**🔴 GENDER IS ALREADY KNOWN AS '{current_gender.upper()}' - DO NOT ASK FOR GENDER! 🔴**\n\n" if current_gender in ['male', 'female'] else ""

    gender_ask_instruction = (
        "**Gender Clarification Strategy (CRITICAL):**\n"
        f"**USER'S LANGUAGE: {current_preferred_lang} - You MUST ask for gender in {target_lang_gender}**\n"
        f"**CURRENT USER GENDER: '{current_gender}'** - This is the KNOWN gender from our database.\n\n"
        f"{gender_known_warning}"
        f"**RULES:**\n"
        f"1. If current_gender is 'male' or 'female' (CURRENT: '{current_gender}'): NEVER use 'ask_gender' or 'initial_greet_and_ask_gender' actions. Proceed directly with the user's request.\n"
        f"2. If current_gender is 'unknown': You may ask for gender politely in early conversation stages.\n\n"
        f"The `current_gender_from_config` for this user is '{current_gender}'. " # Explicitly state the known gender to GPT
        "If `current_gender_from_config` is 'unknown' and the conversation is in its early stages (e.g., first 3-4 interactions), you MUST prioritize politely asking the user for their gender. "
        "Explain *why* you need this: 'ظ„ظ…ط³ط§ط¹ط¯طھظƒ ط¨ط´ظƒظ„ ط£ظپط¶ظ„ ظˆطھظ‚ط¯ظٹظ… ظ…ط¹ظ„ظˆظ…ط§طھ ط¯ظ‚ظٹظ‚ط© ظˆظ…ط®طµطµط© (ظ…ط«ظ„ ط§ظ„ط£ط³ط¹ط§ط± ط§ظ„ط®ط§طµط© ط¨ط¬ظ†ط³ظƒ ط£ظˆ ط§ظ„ط®ط¯ظ…ط§طھ ط§ظ„ظ…طھط§ط­ط© ظ„ظ„ط±ط¬ط§ظ„/ط§ظ„ظ†ط³ط§ط، ظˆطھط¬ظ†ط¨ ط§ظ„ط£ط®ط·ط§ط، ظپظٹ ظ…ط®ط§ط·ط¨طھظƒ)طŒ ظ‡ظ„ ظٹظ…ظƒظ† ط£ظ† طھط®ط¨ط±ظ†ظٹ ظ…ط§ ط¥ط°ط§ ظƒظ†طھظژ ط´ط§ط¨ط§ظ‹ ط£ظ… طµط¨ظٹط©طں' ('To help you better and provide accurate, personalized information (like gender-specific prices or services, and to address you correctly), could you please tell me if you are male or female?'). "
        "Your `action` in this case should be `ask_gender`. Prioritize this question over detailed service information or booking if gender is unknown and relevant for a precise answer. **If `current_gender_from_config` is already 'male' or 'female', you MUST NOT use the `ask_gender` or `initial_greet_and_ask_gender` actions. Assume the gender is known and proceed with the user's request, using the appropriate gender phrasing as defined in the system instruction.**"
    )

    # Language instruction - language already detected, tell GPT to respond in it
    language_response_instruction = f"""
**🌐 LANGUAGE RESPONSE - CRITICAL REQUIREMENT 🌐**

User's language detected as: **{current_preferred_lang}**
You MUST respond in: **{response_language}**

**RESPONSE RULES:**
- If response_language is "ar": Respond in Arabic script (العربية)
- If response_language is "en": Respond in English
- If response_language is "fr": Respond in French

Note: If user wrote in Franco-Arabic (Latin letters for Arabic sounds like "kifak"),
you still respond in Arabic SCRIPT, not Franco.

**YOUR JSON MUST INCLUDE:**
- `detected_language`: "{current_preferred_lang}"
- `bot_reply`: Your response in **{response_language}**

DO NOT detect language yourself - it has already been detected.
"""


    # Combine all system instructions
    system_instruction_final = system_instruction_core + "\n\n" + early_name_instruction + "\n\n" + booking_instruction + "\n\n" + gender_ask_instruction + "\n\n" + language_response_instruction


    messages = [{"role": "system", "content": system_instruction_final}]
    messages.extend(current_context_messages[-config.MAX_CONTEXT_MESSAGES:])

    # Let GPT detect language naturally - no forced language reminder
    messages.append({"role": "user", "content": user_input})
    
    gpt_raw_content = "" # Initialize gpt_raw_content here to make it accessible in except blocks

    # Dynamic model selection based on question complexity
    selected_model, model_metadata = select_optimal_model(
        question=user_input,
        context=current_context_messages,
        user_tier="standard"
    )
    print(f"🤖 Model selected: {selected_model} | Complexity: {model_metadata['complexity']} | Reason: {model_metadata['reason']}")

    try:
        response = await client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=0.7,
            tools=get_openai_tools_schema(),
            tool_choice="auto",
            response_format={"type": "json_object"}
        )
        
        first_response_message = response.choices[0].message
        
        gpt_raw_content = first_response_message.content.strip() if first_response_message.content else ""
        print(f"GPT Raw Response (first pass): {gpt_raw_content}") 

        tool_calls = first_response_message.tool_calls

        parsed_response = {}

        if tool_calls:
            messages.append(first_response_message)

            # Track check_next_appointment result to auto-chain appointment_id for update_appointment_date
            check_next_appointment_result = None

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {} 
                
                # --- NEW LOGIC: Pre-process date/time for create_appointment tool call ---
                if function_name == "create_appointment":
                    # === CRITICAL VALIDATION: Ensure user explicitly provided date/time ===
                    # GPT sometimes makes up dates - we must verify the user actually specified one
                    def user_provided_datetime(messages, user_input):
                        """Check if user explicitly mentioned a date or time in their messages."""
                        # Date/time patterns that indicate user provided a date
                        datetime_patterns = [
                            # Explicit dates
                            r'\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b',  # 21/01, 21-01-2026, etc.
                            r'\b\d{1,2}\s*(?:st|nd|rd|th)?\s*(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',  # 21st january, 21 jan
                            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\b',  # january 21st
                            # Relative dates
                            r'\b(?:today|tomorrow|the day after tomorrow|after tomorrow|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
                            r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
                            # Arabic relative dates
                            r'\b(?:اليوم|بكرا|غدا|بعد بكرا|بعد غدا|الاثنين|الثلاثاء|الاربعاء|الخميس|الجمعة|السبت|الاحد)\b',
                            # Franco-Arab dates (expanded)
                            r'\b(?:bukra|bokra|ba3d bukra|ba3d bokra|lyom|el yom|elyom|alyom)\b',
                            # Franco-Arab time: "aal 3", "3al 3", "saa 3", "el sa3a 3"
                            r'\b(?:aal|3al|3a|saa|sa3a|el\s*sa3a)\s*\d{1,2}\b',
                            # Time patterns
                            r'\b\d{1,2}\s*(?::\d{2})?\s*(?:am|pm|صباحا|مساء|الصبح|بالليل|noon|midnight)\b',
                            r'\bat\s+\d{1,2}(?::\d{2})?\b',  # at 11, at 11:00
                            r'\b(?:morning|afternoon|evening|صباح|مساء)\b',
                            # Simple time reference after relative date (e.g., "bokra 3", "tomorrow 3")
                            r'\b(?:bukra|bokra|tomorrow|غدا|بكرا)\s+(?:aal|3al|at|el|)?\s*\d{1,2}\b',
                        ]

                        # Check user input and recent user messages
                        all_user_text = user_input.lower()
                        for msg in messages:
                            if msg.get("role") == "user":
                                all_user_text += " " + msg.get("content", "").lower()

                        for pattern in datetime_patterns:
                            if re.search(pattern, all_user_text, re.IGNORECASE):
                                print(f"DEBUG: Found date/time pattern in user messages: {pattern}")
                                return True

                        return False

                    # Validate that user actually provided a date/time
                    if not user_provided_datetime(current_context_messages, user_input):
                        print("ERROR: GPT attempted to book without user specifying date/time. Rejecting.")
                        # Return response asking for date/time
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "What date and time would work best for your appointment?" if current_preferred_lang == "en" else
                                        "شو التاريخ والوقت يلي بيناسبك للموعد؟" if current_preferred_lang == "ar" else
                                        "Quel jour et quelle heure vous conviendraient pour le rendez-vous?" if current_preferred_lang == "fr" else
                                        "shu el tarekh w el wa2et li byesbak lal maw3ad?",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # === CRITICAL VALIDATION: Ensure user explicitly provided branch location ===
                    def user_provided_branch(messages, user_input):
                        """Check if user explicitly mentioned a branch location in their messages."""
                        branch_patterns = [
                            # Branch names
                            r'\b(?:beirut|beyrouth|بيروت|bayrut)\b',
                            r'\b(?:manara|منارة|el manara|el-manara)\b',
                            r'\b(?:antelias|انطلياس|antilyas)\b',
                            r'\b(?:center\s*haj|haj\s*building)\b',
                            # Generic branch references with location
                            r'\b(?:branch\s+(?:1|2|one|two))\b',
                            r'\b(?:first\s+branch|second\s+branch)\b',
                            r'\b(?:main\s+branch)\b',
                        ]

                        # Check user input and recent user messages
                        all_user_text = user_input.lower()
                        for msg in messages:
                            if msg.get("role") == "user":
                                all_user_text += " " + msg.get("content", "").lower()

                        for pattern in branch_patterns:
                            if re.search(pattern, all_user_text, re.IGNORECASE):
                                print(f"DEBUG: Found branch pattern in user messages: {pattern}")
                                return True

                        return False

                    # Validate that user actually provided a branch
                    if not user_provided_branch(current_context_messages, user_input):
                        print("ERROR: GPT attempted to book without user specifying branch. Rejecting.")
                        # Return response asking for branch
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "Which branch would you prefer? We have Beirut (Manara) and Antelias (Center Haj Building)." if current_preferred_lang == "en" else
                                        "أي فرع بتفضل؟ عنا بيروت (المنارة) وأنطلياس (سنتر الحاج)." if current_preferred_lang == "ar" else
                                        "Quelle branche préférez-vous? Nous avons Beyrouth (Manara) et Antelias (Center Haj)." if current_preferred_lang == "fr" else
                                        "ayya far3 btfadel? 3anna beirut (manara) w antelias (center haj).",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # Extract customer name and phone from the conversation if not provided in tool args
                    # CRITICAL FIX: For Qiscus, user_id is room_id, NOT phone number
                    # Get actual phone number from user_data_whatsapp
                    phone_number = config.user_data_whatsapp.get(user_id, {}).get('phone_number')
                    
                    # Fallback: If no phone_number stored, check if user_id looks like a phone number
                    if not phone_number:
                        # Check if user_id looks like a phone number (starts with + and has digits)
                        if user_id.startswith('+') or (user_id.replace('+', '').replace('-', '').replace(' ', '').isdigit() and len(user_id) >= 8):
                            phone_number = user_id
                            print(f"DEBUG: Using user_id as phone_number (Meta/Dialog360 format): {phone_number}")
                        else:
                            print(f"ERROR: No phone_number found for user {user_id} and user_id doesn't look like a phone number")
                    else:
                        print(f"DEBUG: Using stored phone_number from user_data: {phone_number}")

                    # CRITICAL FIX: Priority 1 - Use collected name (protected from webhook)
                    user_data_dict = config.user_data_whatsapp.get(user_id, {})
                    customer_name = user_data_dict.get('collected_name')
                    
                    if customer_name:
                        print(f"DEBUG: Using protected collected name: {customer_name}")
                    
                    # Priority 2: Check config.user_names (might be overwritten by webhook)
                    if not customer_name:
                        customer_name = config.user_names.get(user_id)
                        # Skip if Arabic (causes API 500 errors)
                        if customer_name and re.search(r'[\u0600-\u06FF]', customer_name):
                            print(f"WARNING: Skipping Arabic name from config: {customer_name}")
                            customer_name = None
                        elif customer_name:
                            print(f"DEBUG: Using name from config.user_names: {customer_name}")
                    
                    # Priority 3: Search conversation history for Latin name
                    # Check BOTH user messages AND bot messages (GPT might have confirmed the name)
                    if not customer_name:
                        for msg_entry in reversed(current_context_messages + [{"role": "user", "content": user_input}]):
                            msg_content = msg_entry["content"].strip()
                            msg_role = msg_entry["role"]
                            
                            # Pattern 1: User explicitly states their name
                            if msg_role == "user":
                                name_match = re.search(
                                    r'(?:my name is|i am|i\'m|call me|انا اسمي|اسمي|اسمي هو|je m\'appelle|je suis)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})',
                                    msg_content,
                                    re.IGNORECASE | re.UNICODE
                                )
                                if name_match:
                                    potential_name = name_match.group(1).strip()
                                    
                                    # Validate: name should not contain booking-related words
                                    booking_keywords = [
                                        'book', 'appointment', 'schedule', 'reserve', 'موعد', 'حجز',
                                        'want', 'need', 'like', 'please', 'tomorrow', 'today', 'بدي', 'بحب',
                                        'just', 'an', 'the', 'a', 'have', 'get'
                                    ]
                                    
                                    contains_booking_word = any(
                                        keyword in potential_name.lower() 
                                        for keyword in booking_keywords
                                    )
                                    
                                    if not contains_booking_word:
                                        customer_name = potential_name
                                        print(f"DEBUG: Extracted name from user message with prefix: {customer_name}")
                                        break
                            
                            # Pattern 2: Bot confirmed the name (e.g., "Your name is John Smith")
                            elif msg_role == "assistant":
                                name_match = re.search(
                                    r'(?:your name is|you are|you\'re called|اسمك|اسمك هو|ton nom est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})',
                                    msg_content,
                                    re.IGNORECASE | re.UNICODE
                                )
                                if name_match:
                                    potential_name = name_match.group(1).strip()
                                    
                                    # Clean up any trailing punctuation or words
                                    potential_name = re.sub(r'\s+(and|et|و|،|,|\.).*$', '', potential_name, flags=re.IGNORECASE)
                                    
                                    # Validate length
                                    if 2 <= len(potential_name) <= 50:
                                        customer_name = potential_name
                                        print(f"DEBUG: Extracted name from bot confirmation: {customer_name}")
                                        break
                            
                            # Pattern 3: User provides JUST their name (2-4 words, proper capitalization)
                            # This is risky but necessary when user responds to "What is your name?"
                            elif msg_role == "user" and not customer_name:
                                # Check if this looks like a standalone name response
                                words = msg_content.split()
                                if 1 <= len(words) <= 4:
                                    # Must start with capital letter or be Arabic
                                    if (re.match(r'^[A-ZÀ-Ÿا-ي]', msg_content, re.UNICODE) and 
                                        re.match(r'^[A-Za-zÀ-ÿا-ي\s\-\']+$', msg_content, re.UNICODE)):
                                        
                                        # Exclude common words and booking terms
                                        excluded_words = [
                                            'yes', 'no', 'ok', 'okay', 'sure', 'please', 'thanks', 'hello', 'hi',
                                            'book', 'appointment', 'schedule', 'tomorrow', 'today', 'now',
                                            'نعم', 'لا', 'تمام', 'ماشي', 'شكرا', 'مرحبا', 'موعد', 'حجز',
                                            'oui', 'non', 'merci', 'bonjour', 'salut'
                                        ]
                                        
                                        if msg_content.lower() not in excluded_words:
                                            # Check if previous bot message was asking for name
                                            # Look back in conversation for name request
                                            asking_for_name = False
                                            for prev_msg in reversed(current_context_messages):
                                                if prev_msg["role"] == "assistant":
                                                    prev_content = prev_msg["content"].lower()
                                                    if any(phrase in prev_content for phrase in [
                                                        'your name', 'full name', 'what is your name', 'may i have your name',
                                                        'اسمك', 'ما اسمك', 'شو اسمك',
                                                        'votre nom', 'ton nom', 'quel est votre nom'
                                                    ]):
                                                        asking_for_name = True
                                                        break
                                                # Only check last 2 bot messages
                                                if prev_msg["role"] == "assistant":
                                                    break
                                            
                                            if asking_for_name:
                                                customer_name = msg_content.strip()
                                                print(f"DEBUG: Extracted standalone name (response to name question): {customer_name}")
                                                break
                            
                            if customer_name:
                                break
                    # === NEW PATCH: Persist detected customer name ===
                    if customer_name:
                        # Save name in runtime config
                        config.user_data_whatsapp[user_id]["user_name"] = customer_name
                        config.user_names[user_id] = customer_name

                        # Persist to Firestore asynchronously
                        try:
                            from utils.utils import save_user_name_to_firestore
                            await save_user_name_to_firestore(user_id, customer_name)
                        except Exception as e:
                            print(f"⚠️ Could not persist user name for {user_id}: {e}")


                    # Update function_args with inferred phone/name if not present
                    function_args["phone"] = phone_number # Use the extracted/stored phone number
                    
                    # Check if customer exists, if not, create them
                    customer_exists = False
                    customer_gender_for_api = current_gender # Default to current gender
                    if customer_gender_for_api == "unknown":
                        # Attempt to infer from name if needed for create_customer
                        if customer_name:
                            # This is a very basic heuristic; a dedicated service would be better
                            if current_preferred_lang == "ar" or current_preferred_lang == "franco":
                                if re.search(r'\b(ظ…ط­ظ…ظˆط¯|ظ…ط­ظ…ط¯|ط¹ظ„ظٹ|ط£ط­ظ…ط¯|ط®ط§ظ„ط¯|ط±ط¬ظ„|ط´ط¨|ط°ظƒط±)\b', customer_name, re.UNICODE):
                                    customer_gender_for_api = "male"
                                elif re.search(r'\b(ظ„ظٹظ†ط§|ظپط§ط·ظ…ط©|ظ…ط±ظٹظ…|ط³ط§ط±ط©|ط¨ظ†طھ|طµط¨ظٹط©|ط£ظ†ط«ظ‰)\b', customer_name, re.UNICODE):
                                    customer_gender_for_api = "female"
                            elif current_preferred_lang == "en":
                                if re.search(r'\b(john|paul|male|boy)\b', customer_name, re.IGNORECASE):
                                    customer_gender_for_api = "male"
                                elif re.search(r'\b(jane|mary|female|girl)\b', customer_name, re.IGNORECASE):
                                    customer_gender_for_api = "female"
                            
                        if customer_gender_for_api == "unknown":
                            customer_gender_for_api = "male" # Default to male if still unknown, adjust as clinic policy

                    # Ensure gender is in "Male" or "Female" format as required by API
                    if customer_gender_for_api:
                        customer_gender_for_api = customer_gender_for_api.capitalize() # "male" -> "Male"


                    if phone_number:
                        customer_check_response = await api_integrations.get_customer_by_phone(phone=phone_number) # NEW API call
                        if customer_check_response and customer_check_response.get("success") and customer_check_response.get("data"):
                            customer_exists = True
                            print(f"DEBUG: Customer {phone_number} found in API.")
                        else:
                            print(f"DEBUG: Customer {phone_number} not found in API. Attempting to create.")
                            if customer_name and customer_gender_for_api:
                                create_customer_response = await api_integrations.create_customer(
                                    name=customer_name, 
                                    phone=phone_number, 
                                    gender=customer_gender_for_api, # Pass as "Male" or "Female"
                                    branch_id=config.DEFAULT_BRANCH_ID # NEW: Ensure branch_id is passed for customer creation
                                )
                                if create_customer_response and create_customer_response.get("success"):
                                    customer_exists = True
                                    print(f"DEBUG: Successfully created new customer {customer_name} in API.")
                                else:
                                    print(f"ERROR: Failed to create customer {customer_name}: {create_customer_response.get('message', 'Unknown error')}")
                                    messages.append({
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": "create_customer_failed",
                                        "content": json.dumps({"success": False, "message": f"Failed to create customer: {create_customer_response.get('message', 'Unknown error')}"}),
                                    })
                                    # Indicate that booking failed because customer creation failed
                                    parsed_response = {
                                        "action": "ask_for_details_for_booking", # Keep asking for details or suggest human handover
                                        "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظˆط§ط¬ظ‡طھ ظ…ط´ظƒظ„ط© ظپظٹ طھط³ط¬ظٹظ„ ط¨ظٹط§ظ†ط§طھظƒ ظƒط¹ظ…ظٹظ„ ط¬ط¯ظٹط¯. ظٹط±ط¬ظ‰ ط§ظ„طھط£ظƒط¯ ظ…ظ† طµط­ط© ط§ظ„ط§ط³ظ… ظˆط±ظ‚ظ… ط§ظ„ظ‡ط§طھظپطŒ ط£ظˆ ظٹظ…ظƒظ†ظ†ظٹ طھط­ظˆظٹظ„ظƒ ظ„ظ…ظˆط¸ظپ ظ„ظ…ط³ط§ط¹ط¯طھظƒ.",
                                        "detected_language": current_preferred_lang,
                                        "detected_gender": current_gender,
                                        "current_gender_from_config": current_gender
                                    }
                                    return parsed_response
                            else:
                                print("WARNING: Cannot create customer, missing name or gender.")
                                # Use language-specific error messages
                                error_messages = {
                                    "ar": f"ظ„ط£طھظ…ظƒظ† ظ…ظ† ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط£ط­طھط§ط¬ ظ„ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}",
                                    "en": f"To book your appointment, I need your full name{'.' if current_gender != 'unknown' else ' and gender (male or female).'}",
                                    "fr": f"Pour rأ©server votre rendez-vous, j'ai besoin de votre nom complet{'.' if current_gender != 'unknown' else ' et votre sexe (homme ou femme).'}",
                                    "franco": f"ظ„ط­ط¬ط² ظ…ظˆط¹ط¯ظƒطŒ ط¨ط¯ظٹ ط§ط³ظ…ظƒ ط§ظ„ظƒط§ظ…ظ„{'.' if current_gender != 'unknown' else ' ظˆط¬ظ†ط³ظƒ (ط´ط¨ ط£ظˆ طµط¨ظٹط©).'}"
                                }
                                parsed_response = {
                                    "action": "ask_for_details_for_booking",
                                    "bot_reply": error_messages.get(current_preferred_lang, error_messages["en"]),
                                    "detected_language": current_preferred_lang,
                                    "detected_gender": current_gender,
                                    "current_gender_from_config": current_gender
                                }
                                return parsed_response
                    else:
                        print("WARNING: Cannot check or create customer, phone number not found.")
                        # This should rarely happen since phone_number = user_id (WhatsApp ID)
                        error_messages = {
                            "ar": "ط¹ط°ط±ط§ظ‹طŒ ط­ط¯ط«طھ ظ…ط´ظƒظ„ط© ظپظٹ ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… ظ‡ط§طھظپظƒ. ظٹط±ط¬ظ‰ ط§ظ„ظ…ط­ط§ظˆظ„ط© ظ…ط±ط© ط£ط®ط±ظ‰.",
                            "en": "Sorry, there was an issue verifying your phone number. Please try again.",
                            "fr": "Dأ©solأ©, il y a eu un problأ¨me pour vأ©rifier votre numأ©ro de tأ©lأ©phone. Veuillez rأ©essayer.",
                            "franco": "ط¹ط°ط±ط§ظ‹طŒ ظپظٹ ظ…ط´ظƒظ„ط© ط¨ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط±ظ‚ظ… طھظ„ظپظˆظ†ظƒ. ط¬ط±ط¨ ظ…ط±ط© طھط§ظ†ظٹط©."
                        }
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": error_messages.get(current_preferred_lang, error_messages["en"]),
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response

                    # Only proceed to create_appointment if customer_exists is True
                    if not customer_exists:
                        # This should ideally not be reached if previous logic is sound
                        print("ERROR: Customer not created/found, cannot proceed with appointment.")
                        parsed_response = {
                            "action": "human_handover",
                            "bot_reply": "ط¹ط°ط±ظ‹ط§طŒ ظ„ط§ ظٹظ…ظƒظ†ظ†ظٹ ط¥طھظ…ط§ظ… ط§ظ„ط­ط¬ط² ط­ط§ظ„ظٹظ‹ط§. ط³ط£ظ‚ظˆظ… ط¨طھط­ظˆظٹظ„ظƒ ط¥ظ„ظ‰ ط£ط­ط¯ ظ…ظˆط¸ظپظٹظ†ط§ ظ„ظ„ظ…ط³ط§ط¹ط¯ط©.",
                            "detected_language": current_preferred_lang,
                            "detected_gender": current_gender,
                            "current_gender_from_config": current_gender
                        }
                        return parsed_response


                    # NEW: Provide default values for service_id, machine_id, branch_id if missing
                    # Use .get() with a fallback to config defaults
                    function_args["service_id"] = function_args.get("service_id", config.DEFAULT_SERVICE_ID)
                    function_args["machine_id"] = function_args.get("machine_id", config.DEFAULT_MACHINE_ID)
                    function_args["branch_id"] = function_args.get("branch_id", config.DEFAULT_BRANCH_ID)

                    # Date reformatting and validation
                    if "date" in function_args:
                        original_date_str = function_args["date"]
                        try:
                            dt_obj = None
                            # Attempt to parse various common formats GPT might produce given instructions
                            # Primary expectation is 'YYYY-MM-DD HH:MM:SS' but be flexible for GPT's slight deviations
                            if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", original_date_str): # 'YYYY-MM-DD HH:MM:SS'
                                dt_obj = datetime.datetime.strptime(original_date_str, '%Y-%m-%d %H:%M:%S')
                            elif 'T' in original_date_str: # 'YYYY-MM-DDTHH:MM:SS' (ISO format)
                                # Handle timezone info if present by removing it before parsing if not needed
                                if original_date_str.endswith('Z'): # UTC indicator
                                    dt_obj = datetime.datetime.fromisoformat(original_date_str[:-1])
                                else:
                                    dt_obj = datetime.datetime.fromisoformat(original_date_str)
                            elif re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", original_date_str): # 'YYYY-MM-DD HH:MM'
                                dt_obj = datetime.datetime.strptime(original_date_str, '%Y-%m-%d %H:%M')
                                dt_obj = dt_obj.replace(second=0) # Add seconds if missing
                            elif re.match(r"\d{4}-\d{2}-\d{2}", original_date_str): # 'YYYY-MM-DD' (only date provided)
                                dt_obj = datetime.datetime.strptime(original_date_str, '%Y-%m-%d')
                                # Default to a common clinic opening time if only date is provided
                                dt_obj = dt_obj.replace(hour=10, minute=0, second=0) # Default to 10:00:00 AM

                            if dt_obj:
                                # Use Lebanon timezone for all date comparisons
                                now = datetime.datetime.now(LEBANON_TZ).replace(tzinfo=None)  # Naive datetime in Lebanon time
                                print(f"DEBUG: Current Lebanon time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                                # NEW: If the year is in the past, assume current year
                                if dt_obj.year < now.year:
                                    dt_obj = dt_obj.replace(year=now.year)
                                    print(f"WARNING: GPT proposed a past year. Adjusted to current year: {dt_obj}")

                                # If date is today but time is in the past, set to 1 hour from now or next business day morning
                                if dt_obj.date() == now.date() and dt_obj.time() < now.time():
                                    print(f"WARNING: GPT proposed a time in the past for today: {original_date_str}. Adjusting to 1 hour from now.")
                                    dt_obj = now + datetime.timedelta(hours=1)
                                    dt_obj = dt_obj.replace(second=0, microsecond=0) # Clean up seconds/microseconds
                                    # Ensure it's within business hours (e.g., 9 AM - 6 PM). If not, move to next day 10 AM.
                                    if dt_obj.hour < 9 or dt_obj.hour >= 18: 
                                        dt_obj = (now + datetime.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                                    print(f"DEBUG: Adjusted time for today: {dt_obj}")

                                # If date is in the past (e.g. yesterday), push to tomorrow
                                elif dt_obj.date() < now.date():
                                    print(f"WARNING: GPT proposed a past date: {original_date_str}. Adjusting to tomorrow.")
                                    dt_obj = (now + datetime.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                                    print(f"DEBUG: Adjusted past date to tomorrow: {dt_obj}")
                                
                                # Validate: Date not more than 365 days from now
                                if dt_obj > now + datetime.timedelta(days=365):
                                    print(f"WARNING: GPT proposed a date too far in the future: {original_date_str}. Capping at 365 days from now.")
                                    dt_obj = now + datetime.timedelta(days=365) # Max 365 days, keep time
                                    # If the time on that day is past current time, default to 10 AM for consistency
                                    if dt_obj.date() == (now + datetime.timedelta(days=365)).date() and dt_obj.time() < now.time():
                                        dt_obj = dt_obj.replace(hour=10, minute=0, second=0)
                                
                                # Final check to ensure it's strictly after 'now'
                                if dt_obj <= now:
                                    dt_obj = now + datetime.timedelta(minutes=1) # Ensure at least 1 minute into future for API "after now" check
                                    print(f"WARNING: Final date check adjusted to 1 minute from now: {dt_obj}")

                                function_args["date"] = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                                print(f"DEBUG: Reformatted date for {function_name}: {original_date_str} -> {function_args['date']}")
                            else:
                                print(f"WARNING: Could not parse or convert natural language date for strict API format: {original_date_str}. Letting API handle the error.")
                                # If parsing completely failed, we might want to return an error to GPT or handle it.
                                # For now, we'll let the API call proceed with GPT's original string and let the API error handler respond.

                        except Exception as e:
                            print(f"ERROR: Date reformatting/validation exception for '{original_date_str}': {e}. Proceeding with original date string.")
                    
                    # NEW: Remove 'name' from function_args as create_appointment does not accept it directly.
                    # This resolves the `unexpected keyword argument 'name'` error.
                    if 'name' in function_args:
                        print(f"DEBUG: Removing 'name' argument '{function_args['name']}' from create_appointment call as it's not supported.")
                        del function_args['name']

                # --- FIX: Auto-chain appointment_id from check_next_appointment to update_appointment_date ---
                # When GPT calls both tools together, it can't know the real appointment_id until check_next_appointment returns.
                # This code automatically uses the correct appointment_id from the check result.
                if function_name == "update_appointment_date" and check_next_appointment_result:
                    actual_appointment_id = check_next_appointment_result.get("data", {}).get("appointment", {}).get("id")
                    if actual_appointment_id:
                        gpt_provided_id = function_args.get("appointment_id")
                        if gpt_provided_id != actual_appointment_id:
                            print(f"DEBUG: Auto-chaining appointment_id: GPT provided {gpt_provided_id}, actual is {actual_appointment_id}")
                            function_args["appointment_id"] = actual_appointment_id
                        else:
                            print(f"DEBUG: appointment_id already correct: {actual_appointment_id}")

                if hasattr(api_integrations, function_name) and callable(getattr(api_integrations, function_name)):
                    function_to_call = getattr(api_integrations, function_name)
                    print(f"DEBUG: Executing tool: {function_name} with args: {function_args}")
                    
                    try:
                        tool_output = await function_to_call(**function_args)
                        print(f"DEBUG: Tool output for {function_name}: {tool_output}")

                        # Store check_next_appointment result for auto-chaining appointment_id
                        if function_name == "check_next_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            check_next_appointment_result = tool_output
                            print(f"DEBUG: Stored check_next_appointment result for auto-chaining")

                        # 📊 ANALYTICS: Track service when appointment is created
                        if function_name == "create_appointment" and isinstance(tool_output, dict) and tool_output.get("success"):
                            from services.analytics_events import analytics

                            # Get service and machine names from API response
                            appointment_data = tool_output.get("data", {}).get("appointment") or {}
                            service_info = appointment_data.get("service") or {}
                            service_name = service_info.get("name", "unknown_service") if isinstance(service_info, dict) else str(service_info)
                            machine_info = appointment_data.get("machine")
                            # Handle machine being either a string or a dict
                            machine_name = machine_info.get("name", "unassigned") if isinstance(machine_info, dict) else (str(machine_info) if machine_info else "unassigned")

                            print(f"📊 Analytics: Service tracked from appointment - {service_name}, Machine: {machine_name}")
                            
                            # Log appointment booking
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="booked",
                                messages_count=len(current_context_messages)
                            )
                            print(f"📊 Analytics: Appointment booked - {service_name}")
                        
                        # 📊 ANALYTICS: Track appointment reschedule
                        elif function_name == "update_appointment_date" and isinstance(tool_output, dict) and tool_output.get("success"):
                            from services.analytics_events import analytics
                            
                            # Get service from appointment data if available
                            appointment_data = tool_output.get("data", {})
                            service_id = appointment_data.get("service_id")
                            
                            service_map = {
                                1: "laser_hair_removal",
                                2: "tattoo_removal",
                                3: "co2_laser",
                                4: "skin_whitening",
                                5: "botox",
                                6: "fillers"
                            }
                            service_name = service_map.get(service_id, "unknown_service") if service_id else "unknown_service"
                            
                            # Log appointment reschedule
                            analytics.log_appointment(
                                user_id=user_id,
                                service=service_name,
                                status="rescheduled",
                                messages_count=0
                            )
                            print(f"📊 Analytics: Appointment rescheduled - {service_name}")
                        
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps(tool_output),
                            }
                        )
                    except Exception as tool_e:
                        print(f"â‌Œ ERROR executing tool {function_name}: {tool_e}")
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"success": False, "message": f"Error executing tool: {tool_e}"}),
                            }
                        )
                else:
                    print(f"â‌Œ ERROR: Tool function '{function_name}' not found in api_integrations.")
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps({"success": False, "message": f"Tool function '{function_name}' not implemented."}),
                        }
                    )

            second_response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            gpt_raw_content = second_response.choices[0].message.content.strip() if second_response.choices[0].message.content else ""
            print(f"GPT Raw Response (after tool call): {gpt_raw_content}")

            parsed_response = json.loads(gpt_raw_content)
        else:
            parsed_response = json.loads(gpt_raw_content)

        # Language was pre-detected before GPT call - use it directly
        # GPT was instructed to respond in the pre-detected language
        bot_reply = parsed_response.get("bot_reply", "")
        detected_language = current_preferred_lang  # Use pre-detected language
        parsed_response['detected_language'] = detected_language  # Ensure it's in the response
        print(f"🌐 Using pre-detected language: {detected_language}")

        # Ensure current_gender_from_config in the output reflects the *actual* config value
        # This is critical for GPT to "see" the current state of the bot's knowledge about gender.
        parsed_response['current_gender_from_config'] = current_gender

        # CRITICAL FIX: Override GPT's action if it tries to ask for gender when we already know it
        # GPT sometimes ignores the instruction that gender is already known and tries to ask anyway
        if current_gender in ["male", "female"] and parsed_response.get("action") in ["ask_gender", "initial_greet_and_ask_gender"]:
            print(f"⚠️ GPT tried to ask for gender but current_gender is already '{current_gender}'. Overriding action and response.")
            parsed_response["action"] = "provide_info"
            # Replace the entire response since it was asking about gender
            fallback_responses = {
                "en": "I'd be happy to help! What would you like to know?",
                "ar": "بكل سرور! كيف بقدر ساعدك؟",
                "franco": "أكيد! كيف بقدر ساعدك؟",
                "fr": "Avec plaisir! Comment puis-je vous aider?"
            }
            parsed_response["bot_reply"] = fallback_responses.get(current_preferred_lang, fallback_responses["en"])
            print(f"✅ Using fallback response: {parsed_response['bot_reply']}")

        # ADDITIONAL FIX: Remove gender questions from bot_reply when gender is already known
        # GPT may include gender questions in the text even when action is correct
        if current_gender in ["male", "female"]:
            bot_reply = parsed_response.get("bot_reply", "")
            # Patterns to detect gender questions in Arabic, English, and French
            gender_question_patterns = [
                # Arabic patterns
                r'هل\s*(أنت[ِ]?|انت[ي]?)\s*(شب|شاب|صبي[ة]?|ذكر|أنثى|رجل|سيد[ة]?|ولد|بنت)',
                r'(شب|شاب)\s*(أو|ولا|أم)\s*(صبي[ة]?|بنت)',
                r'جنسك|ما\s*هو\s*جنسك',
                r'👦👧',  # Common emoji pattern for gender question
                # English patterns - ORDER MATTERS: comprehensive patterns FIRST
                r'may\s+I\s+ask\s+(if\s+)?you\'?re\s+.*\??',  # "may I ask if you're male or female?"
                r'To\s+give\s+you\s+personalized.*male\s+or\s+female\??',  # Common GPT phrase
                r"(if\s+)?you're\s+(male|female)\s*(or\s+(male|female))?\??",  # "you're male or female?"
                r'male\s+or\s+female\s*\??',  # "male or female?"
                r'are\s*you\s*(male|female|a\s*(man|woman|boy|girl))\??',
                r'(male|female)\s*\?',
                r'your\s*gender',
                r'what\s*is\s*your\s*gender',
                # French patterns
                r'êtes[- ]vous\s*(un\s*homme|une\s*femme)',
                r'(homme|femme)\s*\?',
                r'votre\s*(genre|sexe)',
                # Franco-Arabic patterns
                r'(chab|sabieh)\s*\?',
                r'inta\s*chab\s*(aw|wala)\s*sabieh',
            ]

            # Check if bot_reply contains gender questions
            import re as re_module
            for pattern in gender_question_patterns:
                if re_module.search(pattern, bot_reply, re_module.IGNORECASE | re_module.UNICODE):
                    print(f"⚠️ Detected gender question in bot_reply while gender is already '{current_gender}'. Sanitizing response.")
                    # Remove the gender question portion - keep the rest of the response
                    # Try to preserve meaningful content by removing just the question part
                    sanitized = re_module.sub(pattern, '', bot_reply, flags=re_module.IGNORECASE | re_module.UNICODE)
                    # Clean up any leftover punctuation or awkward spacing
                    sanitized = re_module.sub(r'\s*[،,؟?]\s*$', '', sanitized)  # Remove trailing punctuation
                    sanitized = re_module.sub(r'\s+', ' ', sanitized).strip()  # Normalize spaces

                    # Check if sanitized response is incomplete (ends with dangling words)
                    incomplete_endings = [
                        r"\byou're\s*$", r"\bif you're\s*$", r"\bare you\s*$", r"\bmay I ask\s*$",
                        r"\bask if\s*$", r"\byour\s*$", r"\ba\s*$", r"\ban\s*$", r"\bthe\s*$",
                        r"\bor\s*$", r"\bmale\s+or\s*$", r"\bfemale\s+or\s*$",  # Catches "or", "male or", "female or"
                        r"\bif you're\s+\w+\s+or\s*$",  # Catches "if you're male or"
                        r"\bأنت[ِ]?\s*$", r"\bهل\s*$", r"\bإذا\s*$", r"\bأو\s*$"  # Arabic "or"
                    ]
                    is_incomplete = any(re_module.search(ending, sanitized, re_module.IGNORECASE) for ending in incomplete_endings)

                    if is_incomplete or not sanitized or len(sanitized) <= 10:
                        # Response is incomplete or useless - provide a proper fallback
                        print(f"⚠️ Sanitized response is incomplete or too short. Using fallback response.")
                        fallback_responses = {
                            "en": "I'd be happy to help you with that! Let me provide the information you need.",
                            "ar": "بكل سرور! خليني أعطيك المعلومات اللي بتحتاجها.",
                            "franco": "أكيد! خليني أساعدك.",
                            "fr": "Avec plaisir! Laissez-moi vous aider."
                        }
                        parsed_response["bot_reply"] = fallback_responses.get(current_preferred_lang, fallback_responses["en"])
                        # Change action to trigger re-processing without gender question
                        parsed_response["action"] = "provide_info"
                        print(f"✅ Using fallback response: {parsed_response['bot_reply']}")
                    else:
                        parsed_response["bot_reply"] = sanitized
                        print(f"✅ Sanitized bot_reply: {sanitized[:100]}...")
                    break

        # We allow GPT to detect gender and signal it, but also check for explicit detection for robustness
        # This part ensures that if our local gender recognition service detects a strong gender, it's reflected
        # in the output, potentially overriding GPT's 'null' or 'unknown' if it was less confident.
        if explicitly_detected_gender_from_input and explicitly_detected_gender_from_input in ["male", "female"]:
            parsed_response['detected_gender'] = explicitly_detected_gender_from_input
        elif 'detected_gender' in parsed_response and parsed_response['detected_gender'] not in ["male", "female"]:
            # If GPT returned something like 'unknown' or 'null' for detected_gender, set it to None
            parsed_response['detected_gender'] = None 
        
        if "action" not in parsed_response or "bot_reply" not in parsed_response:
            raise ValueError("GPT response missing required fields (action or bot_reply)")

        # ============================================================
        # LANGUAGE VALIDATION: Regenerate if response is in wrong language
        # ============================================================
        final_bot_reply = parsed_response.get("bot_reply", "")
        is_lang_valid, lang_error = validate_language_match(response_language, final_bot_reply, response_language)

        if not is_lang_valid:
            print(f"⚠️ {lang_error}")
            print(f"🔄 Regenerating response in correct language: {response_language}")

            # Build a strong language-only instruction
            lang_correction_prompt = f"""Your previous response was in the WRONG language.

The user's message was: "{user_input}"
Your response was: "{final_bot_reply}"

You MUST respond in **{response_language.upper()}** ONLY.
- If response_language is "en": Write your ENTIRE response in English. NO Arabic characters.
- If response_language is "ar": Write your ENTIRE response in Arabic script (العربية).
- If response_language is "fr": Write your ENTIRE response in French. NO Arabic characters.

Rewrite your response in the correct language. Return ONLY a JSON object with "action" and "bot_reply"."""

            try:
                correction_response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are a helpful assistant. Respond ONLY in {response_language}. Return JSON with 'action' and 'bot_reply' fields."},
                        {"role": "user", "content": lang_correction_prompt}
                    ],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                corrected_content = correction_response.choices[0].message.content.strip()
                corrected_parsed = json.loads(corrected_content)
                if "bot_reply" in corrected_parsed:
                    parsed_response["bot_reply"] = corrected_parsed["bot_reply"]
                    print(f"✅ Language corrected. New response: {parsed_response['bot_reply'][:100]}...")
            except Exception as lang_fix_err:
                print(f"❌ Failed to correct language: {lang_fix_err}")
                # Keep original response if correction fails

        return parsed_response
    except json.JSONDecodeError as e:
        print(f"â‌Œ JSON Decode Error from GPT chat response: {e}. Raw content: {gpt_raw_content}")
        # NEW: Try to parse a potential plain text reply if JSON fails
        fallback_bot_reply = gpt_raw_content if gpt_raw_content else "Sorry, I encountered a technical issue understanding your request. Please try again or contact our staff directly. ًں™ڈ"
        return {
            "action": "unknown_query", 
            "bot_reply": fallback_bot_reply, 
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender # Pass the actual gender from config
        }
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ ERROR in get_bot_chat_response from GPT: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"   Full traceback:")
        traceback.print_exc()
        print(f"{'='*80}\n")
        return {
            "action": "unknown_query",
            "bot_reply": "Sorry, I encountered an issue understanding your request at the moment. Please try again or contact our staff directly. ًں™ڈ",
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender # Pass the actual gender from config
        }