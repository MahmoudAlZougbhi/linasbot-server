# handlers/text_handlers_respond.py
# Core logic for processing user input and generating bot responses
# AI Smart Employee Architecture: router + state + operational context

from handlers.text_handlers_firestore import *
from services.analytics_events import analytics
from services.language_detection_service import language_detection_service
from services.interaction_flow_logger import log_interaction
from services.dynamic_messages_service import get_dynamic_message
from services.conversation_router import (
    route as router_route,
    is_gender_answer,
    get_gender_from_message,
    GREETING_TEMPLATES,
    FALLBACK_TEMPLATES,
    ASK_CLARIFICATION_TEMPLATES,
)
from utils.datetime_utils import detect_reschedule_intent
import time
import re

PRICE_INTENT_KEYWORDS = [
    "price",
    "prices",
    "cost",
    "how much",
    "pricing",
    "rate",
    "سعر",
    "اسعار",
    "الاسعار",
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
    "as3ar",
    "price list",
]

LASER_HAIR_INTENT_KEYWORDS = [
    "ليزر شعر",
    "إزالة شعر",
    "ازالة شعر",
    "laser hair",
    "hair laser",
    "epilation",
    "laser removal",
    "ليزر",
]

BODY_AREA_HINT_KEYWORDS = [
    "وجه",
    "وش",
    "خد",
    "شنب",
    "دقن",
    "إبط",
    "ابط",
    "بيكيني",
    "حساسة",
    "يد",
    "ايد",
    "ذراع",
    "رجل",
    "فخذ",
    "ظهر",
    "صدر",
    "بطن",
    "رقبة",
    "underarm",
    "arm",
    "arms",
    "leg",
    "legs",
    "face",
    "back",
    "chest",
    "bikini",
    "body",
]

CLINIC_SCOPE_KEYWORDS = [
    "ليزر",
    "laser",
    "epilation",
    "dpl",
    "co2",
    "tattoo",
    "تاتو",
    "وشم",
    "hair",
    "شعر",
    "جلسة",
    "جلسات",
    "session",
    "sessions",
    "سعر",
    "اسعار",
    "price",
    "pricing",
    "cost",
    "موعد",
    "مواعيد",
    "appointment",
    "appointments",
    "حجز",
    "book",
    "booking",
    "فرع",
    "branch",
    "branches",
    "العيادة",
    "المركز",
    "clinic",
    "center",
    "ليناز",
    "لينا",
    "خدمة",
    "خدمات",
    "service",
    "services",
]

OFF_TOPIC_KEYWORDS = [
    "رئيس",
    "رئاسة",
    "سياسة",
    "وزير",
    "حكومة",
    "برلمان",
    "انتخابات",
    "دولة",
    "capital",
    "president",
    "prime minister",
    "government",
    "politics",
    "election",
    "weather",
    "temperature",
    "news",
    "football",
    "soccer",
    "basketball",
    "movie",
    "series",
    "song",
    "bitcoin",
    "crypto",
    "stock",
    "programming",
    "python",
    "java",
    "javascript",
    "math",
    "physics",
    "chemistry",
]

GENERAL_QUESTION_PREFIX_RE = re.compile(
    r"^(?:مين|من\s+هو|من\s+هي|شو|ما\s+هو|ما\s+هي|what|who|where|when|why|how)\b",
    re.IGNORECASE | re.UNICODE,
)

ALLOWED_GENERAL_QUERIES = [
    "شو اسمك",
    "اسمك",
    "من معي",
    "مين معي",
    "who are you",
    "what is your name",
    "what's your name",
    "how are you",
    "كيفك",
    "مرحبا",
    "اهلا",
    "السلام عليكم",
    "merci",
    "thanks",
    "thank you",
]

ASK_ONE_BY_ONE_ACTIONS = {
    "initial_greet_and_ask_gender",
    "ask_gender",
    "ask_for_details_for_booking",
    "ask_for_service_type",
    "ask_for_details",
    "ask_for_tattoo_photo",
    "ask_clarification",
}

BRIEF_REPLY_ACTIONS = {
    "answer_question",
    "normal_chat",
    "provide_info",
    "unknown_query",
    "tool_call",
    "check_customer_status",
}

INTERROGATIVE_PREFIXES = (
    "شو",
    "شو ",
    "أي",
    "اي",
    "هل",
    "ممكن",
    "فينا",
    "قديش",
    "كم",
    "what",
    "which",
    "could",
    "can",
    "where",
    "when",
    "who",
    "how",
)


def _is_price_intent(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in PRICE_INTENT_KEYWORDS)


def _is_laser_hair_intent(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in LASER_HAIR_INTENT_KEYWORDS)


def _has_body_area_hint(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in BODY_AREA_HINT_KEYWORDS)


def _contains_arabic_chars(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(value or "")))


def _latin_name_token_to_arabic(token: str) -> str:
    token = (token or "").strip().lower()
    if not token:
        return ""

    digraph_map = (
        ("tch", "تش"),
        ("sch", "ش"),
        ("sh", "ش"),
        ("kh", "خ"),
        ("gh", "غ"),
        ("th", "ث"),
        ("dh", "ذ"),
        ("ch", "تش"),
        ("ph", "ف"),
        ("qu", "كو"),
        ("oo", "و"),
        ("ou", "و"),
        ("ee", "ي"),
        ("ie", "ي"),
        ("aa", "ا"),
        ("ay", "اي"),
        ("ai", "اي"),
        ("ck", "ك"),
    )
    for latin_seq, arabic_seq in digraph_map:
        token = token.replace(latin_seq, arabic_seq)

    single_map = {
        "a": "ا",
        "b": "ب",
        "c": "ك",
        "d": "د",
        "e": "ي",
        "f": "ف",
        "g": "ج",
        "h": "ه",
        "i": "ي",
        "j": "ج",
        "k": "ك",
        "l": "ل",
        "m": "م",
        "n": "ن",
        "o": "و",
        "p": "ب",
        "q": "ق",
        "r": "ر",
        "s": "س",
        "t": "ت",
        "u": "و",
        "v": "ف",
        "w": "و",
        "x": "كس",
        "y": "ي",
        "z": "ز",
    }

    out = []
    for ch in token:
        if re.match(r"[\u0600-\u06FF]", ch):
            out.append(ch)
            continue
        mapped = single_map.get(ch)
        if mapped:
            out.append(mapped)
    return "".join(out).strip()


def _transliterate_name_to_arabic(name: str) -> str:
    raw_name = str(name or "").strip()
    if not raw_name:
        return ""
    if _contains_arabic_chars(raw_name):
        return raw_name

    normalized = re.sub(r"[^A-Za-zÀ-ÿ\s\-']", " ", raw_name)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""

    arabic_tokens = []
    for token in re.split(r"[\s\-]+", normalized):
        latin_token = token.encode("ascii", "ignore").decode("ascii")
        arabic_token = _latin_name_token_to_arabic(latin_token)
        if arabic_token:
            arabic_tokens.append(arabic_token)

    return " ".join(arabic_tokens).strip()


def _build_arabic_respectful_address(current_gender: str, user_name: str) -> str:
    if current_gender == "male":
        title = "أستاذ"
    elif current_gender == "female":
        title = "عزيزتي"
    else:
        title = "حضرتك"

    normalized_name = str(user_name or "").strip()
    if not normalized_name or normalized_name.lower() in {"client", "unknown customer"}:
        return title

    if _contains_arabic_chars(normalized_name):
        return f"{title} {normalized_name}"

    name_ar = _transliterate_name_to_arabic(normalized_name)
    if name_ar:
        return f"{title} {name_ar}"
    return title


def _build_single_laser_area_question(current_gender: str, user_name: str) -> str:
    respectful_address = _build_arabic_respectful_address(current_gender, user_name)
    verb = "تعملي" if current_gender == "female" else "تعمل"
    return f"أكيد {respectful_address}، ممكن تخبرني شو المنطقة اللي بدك {verb} ليزر شعر عليها؟"


def _is_out_of_clinic_scope_query(text: str) -> bool:
    probe = str(text or "").strip()
    if len(probe) < 3:
        return False

    lowered = probe.lower()

    if any(phrase in lowered for phrase in ALLOWED_GENERAL_QUERIES):
        return False

    if any(keyword in lowered for keyword in CLINIC_SCOPE_KEYWORDS):
        return False

    if any(keyword in lowered for keyword in OFF_TOPIC_KEYWORDS):
        return True

    # Broad general-knowledge question with no clinic context.
    if GENERAL_QUESTION_PREFIX_RE.search(lowered) and len(lowered.split()) >= 3:
        return True

    return False


def _build_out_of_scope_reply(lang: str) -> str:
    messages = {
        "ar": "أنا مخصّصة فقط لخدمات عيادة ليناز ليزر. فيني ساعدك بأي سؤال عن خدمات الليزر، الأسعار، أو المواعيد.",
        "franco": "أنا مخصّصة فقط لخدمات عيادة ليناز ليزر. فيني ساعدك بأي سؤال عن خدمات الليزر، الأسعار، أو المواعيد.",
        "en": "I can only help with Linas Laser clinic services. I can assist with laser services, pricing, and appointments.",
        "fr": "Je peux uniquement aider concernant les services de la clinique Linas Laser : services laser, prix et rendez-vous.",
    }
    return messages.get((lang or "ar").lower(), messages["ar"])


def _clean_reply_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{2,}", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _split_reply_units(text: str) -> list:
    cleaned = _clean_reply_text(text)
    if not cleaned:
        return []
    units = re.split(r"(?:\n+|(?<=[.!؟?])\s+)", cleaned)
    out = []
    for unit in units:
        unit = re.sub(r"^\s*(?:\d+[.)]|[0-9]+️⃣|[-*•])\s*", "", unit.strip())
        if unit:
            out.append(unit)
    return out


def _looks_like_question(unit: str) -> bool:
    probe = str(unit or "").strip()
    if not probe:
        return False
    if "؟" in probe or "?" in probe:
        return True
    lowered = probe.lower()
    return lowered.startswith(INTERROGATIVE_PREFIXES)


def _truncate_chars(text: str, max_chars: int) -> str:
    content = str(text or "").strip()
    if len(content) <= max_chars:
        return content
    trimmed = content[: max_chars - 1].rstrip()
    return f"{trimmed}…"


def _apply_turn_by_turn_policy(action: str, bot_reply: str, lang: str) -> str:
    """
    Enforce concise turn-by-turn messaging:
    - Ask actions: one short question only
    - Answer actions: concise answer (max one follow-up question)
    """
    cleaned = _clean_reply_text(bot_reply)
    if not cleaned:
        return cleaned

    action = str(action or "").strip().lower()
    units = _split_reply_units(cleaned)
    if not units:
        return cleaned

    if action in ASK_ONE_BY_ONE_ACTIONS:
        question_unit = next((u for u in units if _looks_like_question(u)), units[0])
        question_unit = _truncate_chars(question_unit, 220)
        if lang in ("ar", "franco") and ("؟" not in question_unit and "?" not in question_unit):
            question_unit = f"{question_unit}؟"
        return question_unit

    if action in BRIEF_REPLY_ACTIONS:
        looks_verbose = (
            len(cleaned) > 320
            or len(units) > 3
            or bool(re.search(r"(?:^|\n)\s*(?:\d+[.)]|[0-9]+️⃣|[-*•])\s*", cleaned))
        )
        if not looks_verbose:
            return cleaned

        info_unit = next((u for u in units if not _looks_like_question(u)), units[0])
        question_unit = next((u for u in units if _looks_like_question(u) and u != info_unit), "")

        info_unit = _truncate_chars(info_unit, 180)
        if question_unit:
            question_unit = _truncate_chars(question_unit, 140)
            combined = f"{info_unit} {question_unit}".strip()
            return _truncate_chars(combined, 320)
        return info_unit

    return cleaned


async def _process_and_respond(user_id: str, user_name: str, user_input_to_process: str, user_data: dict, send_message_func, send_action_func):
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    # Start timing for response time tracking
    start_time = time.time()
    _dynamic_retrieval_flow_meta = None  # Set when dynamic retrieval is used (for Activity Flow)

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
    router_reply_lang = response_language if response_language in ("ar", "en", "fr") else current_preferred_lang

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
                # Keep Arabic replies fully in Arabic script; do not echo Latin names.
                "ar": "شكراً! 😊 كيف بقدر ساعدك اليوم؟",
                "en": f"Thanks, {extracted_name}! 😊 How can I help you today?",
                "fr": f"Merci, {extracted_name}! 😊 Comment puis-je vous aider aujourd'hui?",
                "franco": "شكراً! 😊 كيف فيني ساعدك اليوم؟"
            }
            
            thanks_message = thanks_messages.get(current_preferred_lang, thanks_messages["ar"])
            await send_message_func(user_id, thanks_message)
            await save_conversation_message_to_firestore(user_id, "ai", thanks_message, current_conversation_id, extracted_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
            
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
            await save_conversation_message_to_firestore(user_id, "ai", error_message, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
            
            return

    # Check if human takeover is active
    if config.user_in_human_takeover_mode.get(user_id, False):
        print(f"[_process_and_respond] INFO: Conversation {current_conversation_id} for user {user_id} is in human takeover mode. AI fallback guard active.")
        # IMPORTANT: During assigned operator takeover, AI must stay silent.
        # We only send waiting auto-reply when takeover is active AND no operator is assigned yet.
        should_send_waiting = False
        try:
            db = get_firestore_db()
            if db and current_conversation_id:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
                candidate_user_ids = []
                for candidate in [canonical_user_id, user_id]:
                    if candidate and candidate not in candidate_user_ids:
                        candidate_user_ids.append(candidate)
                    if candidate and (
                        candidate.startswith("+") or (candidate.isdigit() and len(candidate) >= 10)
                    ):
                        alt_candidate = candidate[1:] if candidate.startswith("+") else f"+{candidate}"
                        if alt_candidate not in candidate_user_ids:
                            candidate_user_ids.append(alt_candidate)

                conv_data = None
                for candidate_user_id in candidate_user_ids:
                    candidate_ref = users_coll.document(candidate_user_id).collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    ).document(current_conversation_id)
                    candidate_snap = await asyncio.to_thread(candidate_ref.get)
                    if candidate_snap.exists:
                        conv_data = candidate_snap.to_dict() or {}
                        break

                if conv_data and conv_data.get("human_takeover_active", False):
                    operator_assigned = bool(conv_data.get("operator_id"))
                    if operator_assigned:
                        print(f"[_process_and_respond] INFO: Operator assigned for {user_id}; AI remains silent.")
                        return
                    should_send_waiting = True
        except Exception as takeover_check_error:
            print(f"[_process_and_respond] ⚠️ Takeover fallback check failed: {takeover_check_error}")

        if should_send_waiting:
            waiting_msg = get_dynamic_message("waiting_queue_message", current_preferred_lang) or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
            await send_message_func(user_id, waiting_msg)
            await save_conversation_message_to_firestore(
                user_id,
                "ai",
                waiting_msg,
                current_conversation_id,
                user_name,
                user_data.get('phone_number'),
                metadata={"handled_by": "ai", "source": "waiting_queue_fallback"},
            )
        return

    # Hard guardrail: refuse clearly out-of-clinic questions before AI call.
    if _is_out_of_clinic_scope_query(user_input_to_process):
        out_of_scope_reply = _build_out_of_scope_reply(current_preferred_lang)
        await send_message_func(user_id, out_of_scope_reply)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            out_of_scope_reply,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "out_of_scope_guard"},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            out_of_scope_reply,
            "out_of_scope_guard",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
        )
        return

    # ===== AI SMART EMPLOYEE: ROUTER (Phase 2, 10) =====
    config.ensure_conversation_state(user_data)
    conv_state = config.get_conversation_state(user_id, user_data)
    ai_primary_mode = bool(getattr(config, "AI_PRIMARY_ORCHESTRATION", True))
    router_action = router_route(user_id, user_input_to_process, conv_state)
    if ai_primary_mode:
        router_action = None

    # Phase 12: Debugging/logging (Plan §18)
    print(f"[_process_and_respond] 📋 ORCHESTRATION LOG:")
    print(f"   - normalized_input: '{user_input_to_process.strip()[:100]}'")
    print(f"   - state_before: gender={conv_state.get('gender')}, awaiting_gender={conv_state.get('awaiting_gender')}, awaiting_clarification={conv_state.get('awaiting_clarification')}, original_question={bool(conv_state.get('original_question'))}")
    print(f"   - ai_primary_mode: {ai_primary_mode}")
    print(f"   - detected_action: {router_action if router_action else 'ai_decides'}")

    # 1. Human handover (top priority) - transfer immediately
    if (not ai_primary_mode) and router_action == "human_handover":
        async def _activate_ai_handover_router(escalation_reason: str, trigger_source: str):
            db = get_firestore_db()
            if db and current_conversation_id:
                try:
                    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                    users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
                    candidate_user_ids = []
                    for c in [canonical_user_id, user_id]:
                        if c and c not in candidate_user_ids:
                            candidate_user_ids.append(c)
                        if c and (c.startswith("+") or (c.isdigit() and len(c) >= 10)):
                            alt = c[1:] if c.startswith("+") else f"+{c}"
                            if alt not in candidate_user_ids:
                                candidate_user_ids.append(alt)
                    for cid in candidate_user_ids:
                        ref = users_coll.document(cid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                        snap = await asyncio.to_thread(ref.get)
                        if snap.exists:
                            await asyncio.to_thread(ref.update, {
                                "status": "waiting_human", "human_takeover_active": True,
                                "human_takeover_requested": True, "operator_id": None,
                                "conversation_state": "waiting_for_operator",
                                "escalation_reason": escalation_reason,
                                "escalation_time": datetime.datetime.now(),
                                "last_updated": datetime.datetime.now(),
                            })
                            break
                except Exception as e:
                    print(f"⚠️ Failed to update handover state: {e}")
            config.user_in_human_takeover_mode[user_id] = True
            notify_human_on_whatsapp(user_name, current_gender, user_input_to_process, type_of_notification=f"AI handover - {escalation_reason}")
            try:
                from services.human_takeover_notification_service import human_takeover_notification_service
                await human_takeover_notification_service.notify_and_audit_handoff(
                    user_id=user_id, user_gender=current_gender, customer_name=user_name,
                    customer_phone=user_data.get('phone_number', 'Unknown'),
                    escalation_reason=escalation_reason, last_message=user_input_to_process,
                    trigger_source=trigger_source, conversation_id=current_conversation_id,
                    extra_details={"action": "router_human_handover"}
                )
            except Exception as notify_error:
                print(f"⚠️ Failed to send handoff: {notify_error}")

        await _activate_ai_handover_router("customer_requested_human", "router_human_handover")
        handoff_msg = {"ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏", "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏", "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏"}
        sent_reply = handoff_msg.get(current_preferred_lang, handoff_msg["ar"])
        await send_message_func(user_id, sent_reply)
        await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        log_report_event("human_handover", user_id, current_gender, {"message": user_input_to_process, "status": "router_direct", "source": "router"})
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        return

    # 2. Greeting only (Phase 7)
    if (not ai_primary_mode) and router_action == "greeting":
        if router_reply_lang in ("ar", "franco"):
            respectful_address = _build_arabic_respectful_address(current_gender, user_name)
            greeting_msg = (
                f"مرحباً {respectful_address}، أنا مروى، المساعد الذكي في ليناز ليزر. كيف فيني ساعدك؟"
            )
        else:
            greeting_msg = get_dynamic_message("router_greeting", router_reply_lang) or GREETING_TEMPLATES.get(router_reply_lang, GREETING_TEMPLATES["ar"])
        await send_message_func(user_id, greeting_msg)
        await save_conversation_message_to_firestore(user_id, "ai", greeting_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai", "source": "router_greeting"})
        log_interaction(
            user_id,
            user_input_to_process,
            greeting_msg,
            "router_greeting",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
        )
        return

    # 3. Fallback (Phase 11)
    if (not ai_primary_mode) and router_action == "fallback":
        fallback_msg = get_dynamic_message("router_fallback", router_reply_lang) or FALLBACK_TEMPLATES.get(router_reply_lang, FALLBACK_TEMPLATES["ar"])
        await send_message_func(user_id, fallback_msg)
        await save_conversation_message_to_firestore(user_id, "ai", fallback_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai", "source": "router_fallback"})
        log_interaction(
            user_id,
            user_input_to_process,
            fallback_msg,
            "router_fallback",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
        )
        return

    # 4. Ask gender (Phase 8)
    if (not ai_primary_mode) and router_action == "ask_gender":
        user_data['original_question'] = user_input_to_process
        user_data['awaiting_gender'] = True
        user_data['last_bot_question_type'] = 'gender'
        user_data['initial_user_query_to_process'] = user_input_to_process  # backward compat
        gender_questions = config.GENDER_QUESTIONS.get(router_reply_lang, config.GENDER_QUESTIONS["ar"])
        import random
        gender_msg = random.choice(gender_questions)
        await send_message_func(user_id, gender_msg)
        await save_conversation_message_to_firestore(user_id, "ai", gender_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai", "source": "router_ask_gender"})
        log_interaction(
            user_id,
            user_input_to_process,
            gender_msg,
            "router_ask_gender",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
        )
        return

    # 5. Ask clarification (Phase 9) - use localized template
    if (not ai_primary_mode) and router_action == "ask_clarification":
        user_data['original_question'] = user_input_to_process
        user_data['awaiting_clarification'] = True
        user_data['last_bot_question_type'] = 'clarification'
        user_data['pending_clarification_query'] = user_input_to_process  # backward compat
        clarification_msg = get_dynamic_message("router_ask_clarification", router_reply_lang) or ASK_CLARIFICATION_TEMPLATES.get(router_reply_lang, ASK_CLARIFICATION_TEMPLATES["ar"])
        await send_message_func(user_id, clarification_msg)
        await save_conversation_message_to_firestore(user_id, "ai", clarification_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai", "source": "router_ask_clarification"})
        log_interaction(
            user_id,
            user_input_to_process,
            clarification_msg,
            "router_ask_clarification",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
        )
        return

    # 6. answer_question (resume_original_question or answer_new_question)
    # When router returns this from awaiting_gender/awaiting_clarification, we MUST use original_question
    _resume_original_question = False
    resume_original = (not ai_primary_mode) and (conv_state.get('awaiting_gender') or conv_state.get('awaiting_clarification'))
    if resume_original:
        orig = conv_state.get('original_question') or user_data.get('original_question') or user_data.get('pending_clarification_query') or user_data.get('initial_user_query_to_process')
        if orig:
            user_data['awaiting_gender'] = False
            user_data['awaiting_clarification'] = False
            user_data['pending_clarification_query'] = None
            user_data['initial_user_query_to_process'] = None
            if conv_state.get('awaiting_gender'):
                detected_g = get_gender_from_message(user_input_to_process)
                if detected_g in ('male', 'female'):
                    config.user_gender[user_id] = detected_g
                    config.user_greeting_stage[user_id] = 2
                    config.gender_attempts[user_id] = 0
                    await user_persistence.save_user_gender(user_id, detected_g, phone=user_data.get('phone_number', user_id), name=user_name)
            user_data['selected_service'] = user_input_to_process  # user's answer often is the service
            # Phase 4: For selector, pass combined context so retrieval fetches right knowledge
            query_to_send_to_gpt = f"Original user question: {orig}\nUser follow-up answer: {user_input_to_process}"
            _resume_original_question = True
            print(f"[_process_and_respond] 📋 state_after (resume): awaiting_gender=False, awaiting_clarification=False, selected_service={user_input_to_process[:50]}")
        else:
            query_to_send_to_gpt = user_input_to_process
            _resume_original_question = False
    else:
        # answer_question but not from awaiting_gender/clarification (answer_new_question)
        query_to_send_to_gpt = user_input_to_process
        _resume_original_question = False

    is_initial_message_for_gpt = (config.user_greeting_stage[user_id] == 1) and (current_gender == "unknown")
    initial_user_query_to_process_original = user_data.get('initial_user_query_to_process')

    awaiting_confirmation = user_data.get('awaiting_human_handover_confirmation', False)
    confirmation_keywords_ar = ["اه", "نعم", "اي", "ايه", "يا ريت", "خلصني", "موافق", "yes", "oui", "ok", "تمام"]
    rejection_keywords_ar = ["لا", "ما بدي", "خليني معك", "مش ضروري", "no", "non"]

    gpt_response_data = {}

    if awaiting_confirmation and not ai_primary_mode:
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
        # Only use raw input when not resuming from router (router already set query_to_send_to_gpt for resume)
        if not _resume_original_question:
            query_to_send_to_gpt = user_input_to_process

        # Restore and combine original question when user replies to clarification (legacy path)
        pending_clarification = user_data.get('pending_clarification_query')
        if pending_clarification:
            query_to_send_to_gpt = f"{pending_clarification}\n[User clarified: {user_input_to_process}]"
            user_data['pending_clarification_query'] = None
            user_data['awaiting_clarification'] = False
            print(f"[_process_and_respond] ✅ Restored original query + clarification: '{query_to_send_to_gpt[:80]}...'")

        # DEBUG: Gender confirmation and original query retrieval
        print(f"[_process_and_respond] 🔍 Gender Check:")
        print(f"  - current_gender: {current_gender}")
        print(f"  - greeting_stage: {config.user_greeting_stage[user_id]}")
        print(f"  - initial_query: {initial_user_query_to_process_original}")

        if (not ai_primary_mode) and current_gender in ["male", "female"] and config.user_greeting_stage[user_id] == 1 and initial_user_query_to_process_original:
            print(f"[_process_and_respond] ✅ Gender confirmed! Answering original query: '{initial_user_query_to_process_original}'")
            user_data['initial_user_query_to_process'] = None
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
                user_data.get('phone_number'),
                metadata={"handled_by": "ai"},
            )

        # Check Q&A Database before calling GPT-4
        # Required flow: ALWAYS try FAQ first. If match >=90% return direct answer, else continue normal flow.
        print(f"[_process_and_respond] 🔍 Checking Q&A DATABASE for: '{query_to_send_to_gpt}'")

        is_reschedule_intent = detect_reschedule_intent(query_to_send_to_gpt)
        is_price_intent = _is_price_intent(query_to_send_to_gpt)
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

            print(f"[_process_and_respond] ✅ Q&A MATCH FOUND!")
            if match_tier == "exact":
                print(f"[_process_and_respond] 📊 Match Score: {match_score:.0%} (exact match)")
            else:
                print(f"[_process_and_respond] 📊 Match Score: {match_score:.0%} (≥90% threshold)")
            print(f"[_process_and_respond] 🎯 Returning Q&A directly")
            print(f"[_process_and_respond] 💰 AI CREDITS SAVED: $0.02-0.05 (NO GPT-4 CALL)")
            print(f"[_process_and_respond] ⚡ Response Time: ~100-200ms (vs 2-5s with GPT-4)")
            print(f"[_process_and_respond] 🎯 Answer: {qa_response[:100]}...")

            await send_message_func(user_id, qa_response)
            qa_pair = match_result.get("qa_pair", {})
            stored_language = match_result.get("matched_language", qa_pair.get("language", "ar"))
            faq_id = qa_pair.get("id")
            if isinstance(faq_id, str) and faq_id.isdigit():
                faq_id = int(faq_id)
            await save_conversation_message_to_firestore(
                user_id, "ai", qa_response,
                current_conversation_id, user_name,
                user_data.get('phone_number'),
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
                }
            )
            await update_dashboard_metric_in_firestore(user_id, "qa_responses_used", 1)
            config.user_greeting_stage[user_id] = 2
            save_for_training_conversation_log(query_to_send_to_gpt, qa_response)
            flow_match_title = "Q&A Match (Exact)" if match_tier == "exact" else "Q&A Match (≥90%)"
            flow_steps = [
                {"step": 1, "title": "User → Bot", "content": query_to_send_to_gpt},
                {"step": 2, "title": flow_match_title, "content": f"Bot matched from Q&A database. Score: {match_score:.0%}. No AI call."},
                {"step": 3, "title": "Bot → User", "content": qa_response},
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
                flow_steps=flow_steps,
            )
            return
        else:
            if ai_primary_mode:
                print(
                    "[_process_and_respond] 🧠 AI-primary mode ON. "
                    "No FAQ match >=90%, continuing AI-normal flow."
                )
            if is_reschedule_intent:
                print(
                    "[_process_and_respond] 🔁 Reschedule intent detected. "
                    "No FAQ match >=90%, continuing booking flow."
                )
            if is_price_intent:
                print(
                    "[_process_and_respond] 💰 Price intent detected. "
                    "No FAQ match >=90%, continuing exact pricing flow."
                )
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
                    merged, clarification, action, dr_flow_meta = await retrieve_and_merge(
                        query_to_send_to_gpt,
                        include_price_hint=is_price_intent,
                        response_lang=current_preferred_lang,
                    )
                    if action == "ask_clarification" and clarification:
                        clarification = _apply_turn_by_turn_policy(
                            "ask_clarification",
                            clarification,
                            current_preferred_lang,
                        )
                        user_data['pending_clarification_query'] = query_to_send_to_gpt
                        user_data['original_question'] = query_to_send_to_gpt
                        user_data['awaiting_clarification'] = True
                        user_data['last_bot_question_type'] = 'clarification'
                        bot_sent = dr_flow_meta.get("bot_sent_to_selector", "")
                        ai_returned = dr_flow_meta.get("selector_ai_raw_response", '{"action": "ask_clarification"}')
                        sel_titles = dr_flow_meta.get("selected_titles") or []
                        ai_sel = f"AI selected: {', '.join(sel_titles)}" if sel_titles else "AI requested clarification."
                        if ai_returned:
                            ai_sel += f"\n\nRaw:\n{ai_returned}"
                        flow_steps = [
                            {"step": 1, "title": "User → Bot", "content": query_to_send_to_gpt},
                            {"step": 2, "title": "Bot → AI (Selector)", "content": bot_sent or "User message + file titles."},
                            {"step": 3, "title": "AI → Bot", "content": ai_sel},
                            {"step": 4, "title": "Bot → User", "content": clarification},
                        ]
                        await send_message_func(user_id, clarification)
                        await save_conversation_message_to_firestore(user_id, "ai", clarification, current_conversation_id, user_name, user_data.get("phone_number"), metadata={"handled_by": "ai"})
                        save_for_training_conversation_log(query_to_send_to_gpt, clarification)
                        log_interaction(
                            user_id,
                            query_to_send_to_gpt,
                            clarification,
                            "dynamic_retrieval",
                            user_name=user_name,
                            user_phone=user_data.get("phone_number"),
                            user_gender=current_gender,
                            customer_exists=user_data.get("crm_customer_exists"),
                            customer_file_status=user_data.get("customer_file_status"),
                            flow_steps=flow_steps,
                        )
                        return
                    custom_context = merged
                    _dynamic_retrieval_flow_meta = dr_flow_meta
                    print(f"[_process_and_respond] 📂 Dynamic retrieval: action={action}, context_len={len(merged) if merged else 0}")
            except Exception as e:
                print(f"[_process_and_respond] ⚠️ Dynamic retrieval fallback: {e}")

            conversation_history = await get_conversation_history_from_firestore(user_id, current_conversation_id, max_messages=10)

            # Phase 3: Build operational context when resuming (Plan §10)
            operational_context = None
            if _resume_original_question:
                orig_q = user_data.get('original_question') or conv_state.get('original_question')
                operational_context = (
                    f"Conversation State:\n"
                    f"- gender: {current_gender}\n"
                    f"- awaiting_gender: false\n"
                    f"- awaiting_clarification: false\n"
                    f"- original_question: \"{orig_q or ''}\"\n"
                    f"- selected_service: \"{user_data.get('selected_service', '')}\"\n"
                    f"- last_bot_question_type: \"{conv_state.get('last_bot_question_type', '')}\"\n\n"
                    f"Current User Message: \"{user_input_to_process}\"\n\n"
                    f"Task: The user previously asked a question. The bot asked for clarification or gender. "
                    f"The user has now answered. Answer the ORIGINAL question. Do not ask for clarification again."
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
            )

    action = gpt_response_data.get("action")
    bot_reply_text = gpt_response_data.get("bot_reply")
    detected_gender_from_gpt = gpt_response_data.get("detected_gender")
    detected_language = gpt_response_data.get("detected_language")
    escalation_reason_from_gpt = gpt_response_data.get("escalation_reason")
    flow_meta = gpt_response_data.get("_flow_meta") or {}

    # Defensive normalization: GPT can occasionally return non-schema actions like "none".
    # If we still have a usable bot reply, treat it as a normal answer instead of failing to fallback.
    known_actions = {
        "initial_greet_and_ask_gender",
        "ask_gender",
        "confirm_gender",
        "confirm_booking_details",
        "human_handover_initial_ask",
        "human_handover_confirmed",
        "return_to_normal_chat",
        "human_handover",
        "ask_for_details_for_booking",
        "ask_for_service_type",
        "ask_for_details",
        "ask_for_tattoo_photo",
        "ask_clarification",
        "answer_question",
        "normal_chat",
        "unknown_query",
        "provide_info",
        "tool_call",
        "check_customer_status",
        "confirm_appointment_reschedule",
        "rate_limit_exceeded",
        "content_moderated",
    }
    action = str(action or "").strip().lower()
    if action not in known_actions:
        if bot_reply_text:
            print(
                f"[_process_and_respond] ⚠️ Unexpected GPT action '{action}'. "
                "Using 'answer_question' since bot_reply is present."
            )
            action = "answer_question"
        else:
            action = "unknown_query"
            bot_reply_text = (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى."
            )

    # Concise guardrail for laser-hair discovery:
    # if user asks generally for laser hair and AI returns a long structured block,
    # force a single focused question about target area.
    context_query = (
        user_data.get("original_question")
        or user_data.get("pending_clarification_query")
        or user_input_to_process
    )
    looks_like_laser_hair_discovery = _is_laser_hair_intent(context_query) and not _has_body_area_hint(context_query)
    looks_over_verbose = bool(
        bot_reply_text
        and (
            len(str(bot_reply_text)) > 260
            or "١️⃣" in str(bot_reply_text)
            or "1️⃣" in str(bot_reply_text)
            or "\n-" in str(bot_reply_text)
        )
    )
    if (
        current_preferred_lang in ("ar", "franco")
        and looks_like_laser_hair_discovery
        and (
            action == "ask_gender"
            or (
                looks_over_verbose
                and action in {
                    "answer_question",
                    "normal_chat",
                    "provide_info",
                    "unknown_query",
                    "ask_for_details_for_booking",
                    "ask_for_details",
                    "ask_clarification",
                }
            )
        )
    ):
        action = "ask_clarification"
        bot_reply_text = _build_single_laser_area_question(current_gender, user_name)

    bot_reply_text = _apply_turn_by_turn_policy(
        action,
        bot_reply_text,
        current_preferred_lang,
    )

    def _build_firestore_user_candidates(canonical_user_id: str, raw_user_id: str) -> list:
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

    async def _activate_ai_handover(escalation_reason: str, trigger_source: str):
        """Switch conversation to waiting_human, notify admins from settings, and write audit."""
        db = get_firestore_db()
        if db and current_conversation_id:
            try:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                app_id_for_firestore = "linas-ai-bot-backend"
                users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
                conv_doc_ref, doc_snap, canonical_user_id = await _resolve_conversation_doc_ref(
                    users_coll,
                    current_conversation_id,
                    canonical_user_id,
                )
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
                if doc_snap.exists:
                    await asyncio.to_thread(conv_doc_ref.update, update_payload)
                    print(f"✅ Conversation {current_conversation_id} set to waiting_human (AI decision)")
                    try:
                        from services.live_chat_service import live_chat_service
                        live_chat_service.invalidate_cache()
                        await live_chat_service._refresh_index_for_conversation(canonical_user_id, current_conversation_id)
                    except Exception as idx_err:
                        print(f"⚠️ Index refresh after AI handover: {idx_err}")
                else:
                    print(f"⚠️ Conversation {current_conversation_id} not found in Firestore (tried canonical + alternate path)")
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
        # AI-primary: AI decides to request gender, backend persists state and executes.
        if not user_data.get('original_question'):
            user_data['original_question'] = user_input_to_process
        user_data['awaiting_gender'] = True
        user_data['awaiting_clarification'] = False
        user_data['last_bot_question_type'] = 'gender'
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action == "confirm_gender":
        # AI-primary: AI confirmed gender and decided the wording.
        if detected_gender_from_gpt and detected_gender_from_gpt in ["male", "female"]:
            await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_data.get('phone_number', user_id), name=user_name)
            print(f"✅ Saved gender '{detected_gender_from_gpt}' for user {user_id} to API")
        user_data['awaiting_gender'] = False
        user_data['last_bot_question_type'] = None
        config.user_greeting_stage[user_id] = 2
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action == "confirm_booking_details":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        config.user_greeting_stage[user_id] = 2

    elif action == "human_handover_initial_ask":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        user_data['awaiting_human_handover_confirmation'] = True

    elif action == "human_handover_confirmed":
        await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "customer_requested_human",
            trigger_source="ai_handover_confirmed"
        )
        # Use standardized handoff message (same as sentiment escalation) - triggers human request
        handoff_msg = get_dynamic_message("human_handover_message", current_preferred_lang) or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
        sent_reply = handoff_msg
        await send_message_func(user_id, handoff_msg)
        await save_conversation_message_to_firestore(user_id, "ai", handoff_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        log_report_event("human_handover", user_id, current_gender, {
            "message": user_input_to_process,
            "status": "confirmed",
            "source": "ai_handover_confirmed"
        })
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)

    elif action == "return_to_normal_chat":
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action == "human_handover":
        await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "ai_decided_handoff",
            trigger_source="ai_handover_direct"
        )
        # Use standardized handoff message (same as sentiment escalation) - triggers human request
        handoff_msg = get_dynamic_message("human_handover_message", current_preferred_lang) or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
        sent_reply = handoff_msg
        await send_message_func(user_id, handoff_msg)
        await save_conversation_message_to_firestore(user_id, "ai", handoff_msg, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        log_report_event("human_handover", user_id, current_gender, {
            "message": user_input_to_process,
            "status": "direct",
            "source": "ai_handover_direct"
        })
        await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)

    elif action in ["ask_for_details_for_booking", "ask_for_service_type", "ask_for_details", "ask_for_tattoo_photo", "ask_clarification"]:
        if not user_data.get('original_question'):
            user_data['original_question'] = user_input_to_process
        user_data['awaiting_clarification'] = True
        user_data['last_bot_question_type'] = 'clarification'
        user_data['pending_clarification_query'] = user_data.get('original_question')
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        config.user_greeting_stage[user_id] = 2

    elif action in ["answer_question", "normal_chat", "unknown_query", "provide_info", "tool_call", "check_customer_status", "confirm_appointment_reschedule"]:
        user_data['awaiting_gender'] = False
        user_data['awaiting_clarification'] = False
        user_data['pending_clarification_query'] = None
        user_data['last_bot_question_type'] = None
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        config.user_greeting_stage[user_id] = 2

    else:
        sent_reply = "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى."
        await send_message_func(user_id, sent_reply)
        await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        print(f"[_process_and_respond] ERROR: User {user_id} received fallback reply due to unexpected action: {action}")

    # Flow logging for dashboard transparency
    response_time_ms = (time.time() - start_time) * 1000
    flow_source = "rate_limit" if action == "rate_limit_exceeded" else "moderation" if action == "content_moderated" else "gpt"
    flow_steps = None
    if _dynamic_retrieval_flow_meta:
        dr = _dynamic_retrieval_flow_meta
        bot_sent_selector = dr.get("bot_sent_to_selector", "")
        ai_selector_return = dr.get("selector_ai_raw_response", "")
        tool_round_trips = flow_meta.get("tool_round_trips") or []
        ai_first = flow_meta.get("ai_first_response")
        ai_error = flow_meta.get("error")
        ai_raw_or_error = flow_meta.get("ai_raw_response") or (f"AI error: {ai_error}" if ai_error else None)
        selected_titles = dr.get("selected_titles") or []
        loaded_content_full = dr.get("loaded_content_full") or ""
        loaded_content_block = (
            "Bot loaded from knowledge/price/style:\n  • " + "\n  • ".join(selected_titles)
            if selected_titles
            else f"Bot used default/general content. Action: {dr.get('action', 'normal')}."
        )
        if loaded_content_full:
            loaded_content_block += (
                f"\n\nFull loaded content sent to AI ({len(loaded_content_full)} chars):\n"
                f"{loaded_content_full}"
            )
        ai_selected_str = f"AI selected from knowledge/price/style:\n  • " + "\n  • ".join(selected_titles) if selected_titles else ""
        if ai_selector_return:
            ai_selected_str += f"\n\nRaw AI response:\n{ai_selector_return}"
        elif not ai_selected_str:
            ai_selected_str = f"Files: {', '.join(dr.get('selected_files') or [])}, action: {dr.get('action', 'normal')}"
        steps = [
            {"step": 1, "title": "User → Bot", "content": user_input_to_process},
            {"step": 2, "title": "Bot → AI (Selector)", "content": bot_sent_selector or "User message + file titles."},
            {"step": 3, "title": "AI → Bot (Selector)", "content": ai_selected_str or "AI returned."},
            {"step": 4, "title": "Bot loaded content", "content": loaded_content_block},
            {"step": 5, "title": "Bot → AI (GPT)", "content": flow_meta.get("bot_sent_to_ai") or flow_meta.get("ai_query_summary") or "Merged content + user query sent to GPT."},
        ]
        step_num = 6
        if tool_round_trips:
            steps.append({"step": step_num, "title": "AI → Bot (requested tools)", "content": ai_first or "AI requested tool calls."})
            step_num += 1
            for tr in tool_round_trips:
                steps.append({"step": step_num, "title": f"AI requested: {tr.get('ai_requested', '?')}", "content": f"Args: {tr.get('args', '{}')}"})
                step_num += 1
                steps.append({"step": step_num, "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})", "content": tr.get("bot_returned", "")})
                step_num += 1
            steps.append({"step": step_num, "title": "AI → Bot (GPT final)", "content": ai_raw_or_error or "(no content)"})
            step_num += 1
        else:
            steps.append({"step": step_num, "title": "AI → Bot (GPT)", "content": ai_raw_or_error or f"GPT returned. Model: {flow_meta.get('model', '?')} | Tokens: {flow_meta.get('tokens', '?')} | Time: {response_time_ms:.0f}ms"})
            step_num += 1
        steps.append({"step": step_num, "title": "Bot → User", "content": sent_reply or "(no response)"})
        flow_steps = steps
    else:
        tool_round_trips = flow_meta.get("tool_round_trips") or []
        ai_first = flow_meta.get("ai_first_response")
        ai_error = flow_meta.get("error")
        ai_raw_or_error = flow_meta.get("ai_raw_response") or (f"AI error: {ai_error}" if ai_error else None)
        steps = [
            {"step": 1, "title": "User → Bot", "content": user_input_to_process},
            {"step": 2, "title": "Bot → AI", "content": flow_meta.get("bot_sent_to_ai") or flow_meta.get("ai_query_summary") or "Query + context sent to GPT."},
        ]
        step_num = 3
        if tool_round_trips:
            steps.append({"step": step_num, "title": "AI → Bot (requested tools)", "content": ai_first or "AI requested tool calls."})
            step_num += 1
            for i, tr in enumerate(tool_round_trips):
                steps.append({
                    "step": step_num,
                    "title": f"AI requested: {tr.get('ai_requested', '?')}",
                    "content": f"Args: {tr.get('args', '{}')}",
                })
                step_num += 1
                steps.append({
                    "step": step_num,
                    "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})",
                    "content": tr.get("bot_returned", ""),
                })
                step_num += 1
            steps.append({"step": step_num, "title": "AI → Bot (final response)", "content": ai_raw_or_error or "(no content)"})
            step_num += 1
        else:
            steps.append({"step": step_num, "title": "AI → Bot", "content": ai_raw_or_error or f"GPT returned. Model: {flow_meta.get('model', '?')} | Tokens: {flow_meta.get('tokens', '?')} | Time: {response_time_ms:.0f}ms"})
            step_num += 1
        steps.append({"step": step_num, "title": "Bot → User", "content": sent_reply or "(no response)"})
        flow_steps = steps
    log_interaction(
        user_id,
        user_input_to_process,
        sent_reply or "",
        flow_source,
        user_name=user_name,
        user_phone=user_data.get("phone_number"),
        user_gender=current_gender,
        customer_exists=user_data.get("crm_customer_exists"),
        customer_file_status=user_data.get("customer_file_status"),
        ai_query_summary=flow_meta.get("ai_query_summary"),
        bot_sent_to_ai_full=flow_meta.get("bot_sent_to_ai"),
        ai_raw_response=flow_meta.get("ai_raw_response"),
        model=flow_meta.get("model"),
        tokens=flow_meta.get("tokens"),
        prompt_tokens=flow_meta.get("prompt_tokens"),
        completion_tokens=flow_meta.get("completion_tokens"),
        response_time_ms=response_time_ms,
        tool_calls=flow_meta.get("tool_calls"),
        flow_steps=flow_steps,
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
