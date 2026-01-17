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

_custom_qa_cache = {}

# user_id is the WhatsApp phone number
async def get_bot_chat_response(user_id: str, user_input: str, current_context_messages: list, current_gender: str, current_preferred_lang: str, is_initial_message_after_start: bool, initial_user_query_to_process: str = None) -> dict:
    user_name = config.user_names.get(user_id, "client") 
    current_gender_attempts = config.gender_attempts.get(user_id, 0)
    
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
        print(f"⚠️ Content flagged for user {user_id}: {moderation_result}")
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
    
    # Get the core system instruction from utils.py, which now contains the JSON output format requirement.
    # Pass the current_gender directly to get_system_instruction so it can formulate the gender instruction based on the actual known gender.
    system_instruction_core = get_system_instruction(user_id, current_preferred_lang)

    # Enhanced booking instruction: GPT is responsible for parsing date/time from natural language
    booking_instruction = (
        "**Appointment Booking Process:**\n"
        "When the user expresses intent to book an appointment, you are responsible for gathering *all* necessary details for the `create_appointment` tool. These details are: Full Name, Phone Number, Specific Service, Body Area(s) (if applicable for laser hair removal), Preferred Machine (Neo, Quadro, or Trio), Preferred Branch, and an Exact Date and Time.\n"
        "**Date and Time Conversion (CRITICAL):** You MUST intelligently convert any natural language date/time expressions (e.g., 'tomorrow at 3 PM', 'next Friday', 'in 3 days', 'tonight at 7:30 PM') into the exact 'YYYY-MM-DD HH:MM:SS' format. Always use the *current actual date and time* as your reference point for 'tomorrow', 'next week', etc. The appointment date must be in the future and not more than 365 days from today. If the user provides only a day (e.g., 'tomorrow'), suggest a default time like '10:00:00' or '14:00:00 (2 PM)'. If only a time is given (e.g., 'at 5 PM'), assume today's date if it's in the future, otherwise assume tomorrow. You must confirm the extracted date and time in your `bot_reply` before trying to book.\n"
        "**Confirmation and Tool Call:** Do NOT call `create_appointment` until you have *all* required parameters (`phone`, `service_id`, `machine_id`, `branch_id`, `date`, `name` if new customer) and you have *confirmed them with the user* in your `bot_reply`. If details are missing, your `action` should be `ask_for_details_for_booking`, and your `bot_reply` should ask for the *next specific missing piece of information*. For example, 'تمام، وأي جهاز بتفضل؟' or 'وما هو اسمك الكامل ورقم هاتفك؟'. If the user says 'ok book it' but not all info is there, you still ask for the missing parts.\n"
        "**Example of Confirmation:** If user says 'ok book me for tomorrow 1pm', and you know all other details, your `bot_reply` should be: 'تمام، إذاً موعدك بكرا السبت 28 تموز الساعة 1:00 بعد الظهر في فرع المنارة على جهاز النيو، صحيح؟' and `action` should be `confirm_booking_details`. Only call the tool (`create_appointment`) after final confirmation by the user (e.g., 'yes', 'ok', 'confirm'). If you have all information and user confirms, then `action` should be `tool_call` and `bot_reply` should inform the user that you are booking."
    )

    # Enhanced gender ask instruction: GPT is responsible for when and how to ask
    gender_ask_instruction = (
        "**Gender Clarification Strategy (CRITICAL):**\n"
        f"The `current_gender_from_config` for this user is '{current_gender}'. " # Explicitly state the known gender to GPT
        "If `current_gender_from_config` is 'unknown' and the conversation is in its early stages (e.g., first 3-4 interactions), you MUST prioritize politely asking the user for their gender. "
        "Explain *why* you need this: 'لمساعدتك بشكل أفضل وتقديم معلومات دقيقة ومخصصة (مثل الأسعار الخاصة بجنسك أو الخدمات المتاحة للرجال/النساء وتجنب الأخطاء في مخاطبتك)، هل يمكن أن تخبرني ما إذا كنتَ شاباً أم صبية؟' ('To help you better and provide accurate, personalized information (like gender-specific prices or services, and to address you correctly), could you please tell me if you are male or female?'). "
        "Your `action` in this case should be `ask_gender`. Prioritize this question over detailed service information or booking if gender is unknown and relevant for a precise answer. **If `current_gender_from_config` is already 'male' or 'female', you MUST NOT use the `ask_gender` or `initial_greet_and_ask_gender` actions. Assume the gender is known and proceed with the user's request, using the appropriate gender phrasing as defined in the system instruction.**"
    )

    # NEW: Instruction for Franco Arabic response style
    franco_arabic_response_instruction = ""
    if current_preferred_lang == "franco":
        franco_arabic_response_instruction = (
            "**Franco Arabic Response Style:** The user's detected language is Franco Arabic. This means your replies, especially in the `bot_reply` field, should be in **colloquial Lebanese Arabic dialect**, but written using Arabic script, NOT Latin (Franco Arabic) characters. For example, if the user says 'Kifak?', you should reply with 'كيفك؟' NOT 'Kifak?'. Focus on natural, everyday Lebanese expressions. Ensure your `detected_language` is still 'franco' in the JSON, but the `bot_reply` content is Arabic. If the original text was in Franco Arabic, convert it to colloquial Arabic script in your response."
        )


    # Combine all system instructions
    system_instruction_final = system_instruction_core + "\n\n" + booking_instruction + "\n\n" + gender_ask_instruction + "\n\n" + franco_arabic_response_instruction


    messages = [{"role": "system", "content": system_instruction_final}]
    messages.extend(current_context_messages[-config.MAX_CONTEXT_MESSAGES:]) 
    messages.append({"role": "user", "content": user_input})
    
    gpt_raw_content = "" # Initialize gpt_raw_content here to make it accessible in except blocks
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
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

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {} 
                
                # --- NEW LOGIC: Pre-process date/time for create_appointment tool call ---
                if function_name == "create_appointment":
                    # Extract customer name and phone from the conversation if not provided in tool args
                    # user_id is the phone number from WhatsApp
                    phone_number = user_id # Use the user's WhatsApp ID directly as phone number

                    # Get customer name from GPT's function arguments first
                    customer_name = function_args.get("name")
                    print(f"DEBUG: Customer name from GPT arguments: {customer_name}")
                    
                    # If GPT didn't provide name, try to extract from conversation history
                    if not customer_name:
                        print(f"DEBUG: Name not in GPT args, searching conversation history...")
                        for msg_entry in reversed(current_context_messages + [{"role": "user", "content": user_input}]):
                            if msg_entry["role"] == "user":
                                # Improved regex: match names with or without prefix
                                name_match = re.search(r'(?:my name is|انا اسمي|اسمي|i am|i\'m)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', msg_entry["content"], re.IGNORECASE | re.UNICODE)
                                if not name_match:
                                    # Try Arabic names pattern
                                    name_match = re.search(r'(?:اسمي|انا)?\s*([ا-ي]+(?:\s+[ا-ي]+)+)', msg_entry["content"], re.UNICODE)
                                
                                if name_match:
                                    customer_name = name_match.group(1).strip()
                                    print(f"DEBUG: Inferred customer name from context: {customer_name}")
                                    break
                    
                    # Update function_args with inferred phone/name if not present
                    function_args["phone"] = phone_number # Always use user_id as phone number
                    
                    # Check if customer exists, if not, create them
                    customer_exists = False
                    customer_gender_for_api = current_gender # Default to current gender
                    if customer_gender_for_api == "unknown":
                        # Attempt to infer from name if needed for create_customer
                        if customer_name:
                            # This is a very basic heuristic; a dedicated service would be better
                            if current_preferred_lang == "ar" or current_preferred_lang == "franco":
                                if re.search(r'\b(محمود|محمد|علي|أحمد|خالد|رجل|شب|ذكر)\b', customer_name, re.UNICODE):
                                    customer_gender_for_api = "male"
                                elif re.search(r'\b(لينا|فاطمة|مريم|سارة|بنت|صبية|أنثى)\b', customer_name, re.UNICODE):
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
                                        "bot_reply": "عذرًا، واجهت مشكلة في تسجيل بياناتك كعميل جديد. يرجى التأكد من صحة الاسم ورقم الهاتف، أو يمكنني تحويلك لموظف لمساعدتك.",
                                        "detected_language": current_preferred_lang,
                                        "detected_gender": current_gender,
                                        "current_gender_from_config": current_gender
                                    }
                                    return parsed_response
                            else:
                                print("WARNING: Cannot create customer, missing name or gender.")
                                parsed_response = {
                                    "action": "ask_for_details_for_booking",
                                    "bot_reply": "لأتمكن من حجز موعد، أحتاج لاسمك الكامل ورقم هاتفك وجنسك (شب أو صبية).",
                                    "detected_language": current_preferred_lang,
                                    "detected_gender": current_gender,
                                    "current_gender_from_config": current_gender
                                }
                                return parsed_response
                    else:
                        print("WARNING: Cannot check or create customer, phone number not found.")
                        parsed_response = {
                            "action": "ask_for_details_for_booking",
                            "bot_reply": "الرجاء تزويدي برقم هاتفك أولاً لأتمكن من مساعدتك في حجز الموعد.",
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
                            "bot_reply": "عذرًا، لا يمكنني إتمام الحجز حاليًا. سأقوم بتحويلك إلى أحد موظفينا للمساعدة.",
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
                                now = datetime.datetime.now()
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


                if hasattr(api_integrations, function_name) and callable(getattr(api_integrations, function_name)):
                    function_to_call = getattr(api_integrations, function_name)
                    print(f"DEBUG: Executing tool: {function_name} with args: {function_args}")
                    
                    try:
                        tool_output = await function_to_call(**function_args)
                        print(f"DEBUG: Tool output for {function_name}: {tool_output}")
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps(tool_output),
                            }
                        )
                    except Exception as tool_e:
                        print(f"❌ ERROR executing tool {function_name}: {tool_e}")
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps({"success": False, "message": f"Error executing tool: {tool_e}"}),
                            }
                        )
                else:
                    print(f"❌ ERROR: Tool function '{function_name}' not found in api_integrations.")
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
        
        # Ensure current_gender_from_config in the output reflects the *actual* config value
        # This is critical for GPT to "see" the current state of the bot's knowledge about gender.
        parsed_response['current_gender_from_config'] = current_gender
        
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
        
        return parsed_response
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error from GPT chat response: {e}. Raw content: {gpt_raw_content}")
        # NEW: Try to parse a potential plain text reply if JSON fails
        fallback_bot_reply = gpt_raw_content if gpt_raw_content else "Sorry, I encountered a technical issue understanding your request. Please try again or contact our staff directly. 🙏"
        return {
            "action": "unknown_query", 
            "bot_reply": fallback_bot_reply, 
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender # Pass the actual gender from config
        }
    except Exception as e:
        print(f"❌ ERROR in get_bot_chat_response from GPT: {e}")
        return {
            "action": "unknown_query", 
            "bot_reply": "Sorry, I encountered an issue understanding your request at the moment. Please try again or contact our staff directly. 🙏", 
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender # Pass the actual gender from config
        }