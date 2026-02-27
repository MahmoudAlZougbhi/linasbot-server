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
from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
    now_in_bot_tz,
    parse_datetime_flexible,
    resolve_relative_datetime,
    text_mentions_datetime,
)

# Import local Q&A service for context injection
from services.local_qa_service import local_qa_service

# Import dynamic model selector for cost optimization
from services.dynamic_model_selector import select_optimal_model

# Fixed bot timezone (UTC+0200) for all booking day comparisons
BOOKING_TZ = BOT_FIXED_TZ

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
        parts = user_name.split()
        customer_first_name = parts[0] if parts else user_name  # "Nour Jaffala" -> "Nour"
    
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

    # Build dynamic customer context - just the VALUES, rules are in style_guide.txt
    name_is_known = user_name and user_name != "client"
    current_local_time = now_in_bot_tz()
    current_date_str = current_local_time.strftime("%Y-%m-%d")
    current_time_str = current_local_time.strftime("%H:%M:%S")
    current_day_name = current_local_time.strftime("%A")

    # Dynamic customer status block - provides current values for the rules defined in style_guide.txt
    dynamic_customer_context = (
        "**📋 CURRENT CUSTOMER STATUS (Use these values when applying the rules from the Style Guide):**\n"
        f"- **Customer Name**: {'KNOWN - ' + user_name + ' (First name: ' + str(customer_first_name) + '). Do NOT ask for name again.' if name_is_known else 'NOT KNOWN - You MUST ask for their full name (see Name Capture Rules in Style Guide)'}\n"
        f"- **Customer Phone**: '{customer_phone_clean}' - Use this for ALL tool calls (check_next_appointment, create_appointment, update_appointment_date). Do NOT ask for phone number.\n"
        f"- **Gender**: '{current_gender}'"
        + (" - GENDER IS ALREADY KNOWN. NEVER ask for gender again!\n" if current_gender in ['male', 'female'] else " - UNKNOWN. Follow gender collection rules in Style Guide.\n")
        + f"- **Language**: Detected as '{current_preferred_lang}' - You MUST respond in: '{response_language}'\n"
        f"- **current_gender_from_config**: '{current_gender}'\n"
        f"- **detected_language**: '{current_preferred_lang}'\n"
        f"**🕐 CURRENT DATE AND TIME (UTC+0200): {current_day_name}, {current_date_str} at {current_time_str}**\n"
    )

    # Combine system instruction with dynamic context
    system_instruction_final = system_instruction_core + "\n\n" + dynamic_customer_context

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
        
        if not response.choices:
            raise ValueError("GPT returned no choices")
        first_response_message = response.choices[0].message
        
        gpt_raw_content = first_response_message.content.strip() if first_response_message.content else ""
        print(f"GPT Raw Response (first pass): {gpt_raw_content}") 

        tool_calls = first_response_message.tool_calls

        parsed_response = {}

        if tool_calls:
            messages.append(first_response_message)

            # Track check_next_appointment result to auto-chain appointment_id for update_appointment_date
            check_next_appointment_result = None

            def collect_user_datetime_text(context_messages: list, latest_user_input: str) -> str:
                """
                Collect recent user text for date intent detection.
                Keeps chronology and ends with latest user input so the newest
                'today/tomorrow' intent wins over stale history.
                """
                recent_user_messages = []
                for msg in context_messages[-12:]:
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        recent_user_messages.append(content.strip())

                # Keep only the most recent few user turns to avoid stale date leakage.
                recent_user_messages = recent_user_messages[-4:]

                latest_clean = (latest_user_input or "").strip()
                if latest_clean and (not recent_user_messages or recent_user_messages[-1] != latest_clean):
                    recent_user_messages.append(latest_clean)

                return " ".join(recent_user_messages).strip()

            def normalize_tool_date(function_name: str, function_args: dict, all_user_text: str) -> None:
                """
                Normalize tool date using fixed +0200 timezone and multilingual relative phrases.
                Keeps original date if parsing fails.
                """
                if "date" not in function_args:
                    return

                original_date_str = str(function_args["date"]).strip()
                if not original_date_str:
                    return

                now = now_in_bot_tz()
                dt_obj = resolve_relative_datetime(all_user_text, reference=now)
                if dt_obj:
                    print(f"DEBUG: Resolved relative datetime from user text ({function_name}): {all_user_text} -> {dt_obj}")
                else:
                    dt_obj = parse_datetime_flexible(original_date_str)
                    if not dt_obj:
                        print(f"WARNING: Could not parse tool date '{original_date_str}' for {function_name}. Keeping original.")
                        return
                    dt_obj = align_datetime_to_day_reference(dt_obj, all_user_text, reference=now)

                # If GPT provided a past year, keep intent but move to current year.
                if dt_obj.year < now.year:
                    dt_obj = dt_obj.replace(year=now.year)
                    print(f"WARNING: GPT proposed past year. Adjusted to current year: {dt_obj}")

                # Cap to 365 days ahead.
                max_allowed = now + datetime.timedelta(days=365)
                if dt_obj > max_allowed:
                    dt_obj = max_allowed.replace(second=0, microsecond=0)
                    print(f"WARNING: Date too far in future. Capped to: {dt_obj}")

                # Must stay in the future for API validation.
                if dt_obj <= now:
                    dt_obj = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
                    print(f"WARNING: Date was not in future. Adjusted to: {dt_obj}")

                function_args["date"] = dt_obj.astimezone(BOOKING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                print(f"DEBUG: Normalized date for {function_name}: {original_date_str} -> {function_args['date']}")

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                all_user_text_for_date = collect_user_datetime_text(current_context_messages, user_input)
                
                # --- NEW LOGIC: Pre-process date/time for create_appointment tool call ---
                if function_name == "create_appointment":
                    # === CRITICAL VALIDATION: Ensure user explicitly provided date/time ===
                    # GPT sometimes makes up dates - we must verify the user actually specified one
                    def user_provided_datetime(messages, user_input):
                        """Check if user explicitly mentioned date/time in multilingual text."""
                        all_user_text = collect_user_datetime_text(messages, user_input)
                        has_datetime_hint = text_mentions_datetime(all_user_text)
                        if has_datetime_hint:
                            print(f"DEBUG: Date/time hint detected in user messages: {all_user_text}")
                        return has_datetime_hint

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
                                    r"(?:my name is|i am|i'm|call me|انا اسمي|اسمي|اسمي هو|je\s*m['\s]?appelle|je suis|moi c'est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
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

                    # Date normalization and intent alignment (+0200)
                    normalize_tool_date(function_name, function_args, all_user_text_for_date)
                    
                    # NEW: Remove 'name' from function_args as create_appointment does not accept it directly.
                    # This resolves the `unexpected keyword argument 'name'` error.
                    if 'name' in function_args:
                        print(f"DEBUG: Removing 'name' argument '{function_args['name']}' from create_appointment call as it's not supported.")
                        del function_args['name']

                if function_name == "update_appointment_date":
                    normalize_tool_date(function_name, function_args, all_user_text_for_date)

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
            if not second_response.choices:
                raise ValueError("GPT returned no choices (after tool call)")
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
        # Instead of a generic fallback, re-call GPT with explicit context to answer the user's question
        if current_gender in ["male", "female"] and parsed_response.get("action") in ["ask_gender", "initial_greet_and_ask_gender"]:
            print(f"⚠️ GPT tried to ask for gender but current_gender is already '{current_gender}'. Re-calling GPT with explicit context.")

            # Build a focused re-call prompt that preserves context
            gender_word = "male" if current_gender == "male" else "female"
            recall_system_prompt = f"""You are a helpful assistant for Lina's Laser Center.

CRITICAL: The user's gender is ALREADY KNOWN as {gender_word.upper()}. Do NOT ask for gender.

The user just sent a message. Answer their question or continue the conversation naturally.
If they mentioned a service (tattoo removal, hair removal, etc.), proceed with booking flow - ask for date/time, branch, etc.

Respond in {response_language}. Return JSON with "action" and "bot_reply" fields.
For booking-related responses, use action="ask_for_details_for_booking".
For general answers, use action="answer_question"."""

            # Include last few messages for context
            context_summary = ""
            for msg in current_context_messages[-4:]:
                role = "User" if msg.get("role") == "user" else "Bot"
                context_summary += f"{role}: {msg.get('content', '')[:100]}\n"

            recall_user_prompt = f"""Recent conversation:
{context_summary}
User's latest message: {user_input}

Answer the user's question or continue the booking flow. Do NOT ask for gender."""

            try:
                recall_response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": recall_system_prompt},
                        {"role": "user", "content": recall_user_prompt}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                if not recall_response.choices:
                    raise ValueError("GPT recall returned no choices")
                recall_content = recall_response.choices[0].message.content.strip()
                recall_parsed = json.loads(recall_content)

                if "bot_reply" in recall_parsed:
                    parsed_response["bot_reply"] = recall_parsed["bot_reply"]
                    parsed_response["action"] = recall_parsed.get("action", "answer_question")
                    print(f"✅ Re-call successful. New response: {parsed_response['bot_reply'][:100]}...")
                else:
                    raise ValueError("Re-call response missing bot_reply")

            except Exception as recall_err:
                print(f"❌ Re-call failed: {recall_err}. Using fallback.")
                parsed_response["action"] = "provide_info"
                fallback_responses = {
                    "en": "I'd be happy to help! What would you like to know?",
                    "ar": "بكل سرور! كيف بقدر ساعدك؟",
                    "franco": "أكيد! كيف بقدر ساعدك؟",
                    "fr": "Avec plaisir! Comment puis-je vous aider?"
                }
                parsed_response["bot_reply"] = fallback_responses.get(current_preferred_lang, fallback_responses["en"])

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
                        # Response is incomplete or useless - re-call GPT with context
                        print(f"⚠️ Sanitized response is incomplete or too short. Re-calling GPT with context.")

                        # Build a focused re-call prompt
                        gender_word = "male" if current_gender == "male" else "female"
                        recall_system = f"""You are a helpful assistant for Lina's Laser Center.
The user's gender is ALREADY KNOWN as {gender_word.upper()}. Do NOT ask for gender.
Answer the user's question directly. Respond in {response_language}.
Return JSON with "action" and "bot_reply" fields."""

                        context_msgs = ""
                        for msg in current_context_messages[-3:]:
                            role = "User" if msg.get("role") == "user" else "Bot"
                            context_msgs += f"{role}: {msg.get('content', '')[:80]}\n"

                        try:
                            recall_resp = await client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[
                                    {"role": "system", "content": recall_system},
                                    {"role": "user", "content": f"Context:\n{context_msgs}\nUser: {user_input}\n\nAnswer directly without asking for gender."}
                                ],
                                temperature=0.7,
                                response_format={"type": "json_object"}
                            )
                            if not recall_resp.choices:
                                raise ValueError("GPT recall returned no choices")
                            recall_data = json.loads(recall_resp.choices[0].message.content.strip())
                            if "bot_reply" in recall_data:
                                parsed_response["bot_reply"] = recall_data["bot_reply"]
                                parsed_response["action"] = recall_data.get("action", "answer_question")
                                print(f"✅ Re-call successful: {parsed_response['bot_reply'][:80]}...")
                            else:
                                raise ValueError("Missing bot_reply")
                        except Exception as e:
                            print(f"❌ Re-call failed: {e}. Using fallback.")
                            fallback_responses = {
                                "en": "I'd be happy to help you with that! Let me provide the information you need.",
                                "ar": "بكل سرور! خليني أعطيك المعلومات اللي بتحتاجها.",
                                "franco": "أكيد! خليني أساعدك.",
                                "fr": "Avec plaisir! Laissez-moi vous aider."
                            }
                            parsed_response["bot_reply"] = fallback_responses.get(current_preferred_lang, fallback_responses["en"])
                            parsed_response["action"] = "provide_info"
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
                if not correction_response.choices:
                    raise ValueError("GPT language correction returned no choices")
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