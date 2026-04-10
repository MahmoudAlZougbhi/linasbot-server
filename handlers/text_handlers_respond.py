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
import json


def _parse_tool_round_bot_returned(bot_returned: str):
    if not bot_returned or not isinstance(bot_returned, str):
        return None
    try:
        return json.loads(bot_returned)
    except (json.JSONDecodeError, TypeError):
        return None


def _flow_meta_has_crm_booking_confirmation(flow_meta: dict) -> bool:
    """
    True when this GPT turn actually ran submit_booking_intent (or legacy create_appointment)
    and the tool JSON reports CRM booked success.
    """
    for tr in flow_meta.get("tool_round_trips") or []:
        name = str(tr.get("ai_requested") or "").strip()
        if name not in ("submit_booking_intent", "create_appointment"):
            continue
        po = _parse_tool_round_bot_returned(tr.get("bot_returned") or "")
        if isinstance(po, dict) and po.get("success") is True and po.get("booking_flow_state") == "booked":
            return True
    return False


def _booking_not_confirmed_safe_reply(lang: str) -> str:
    """User-facing text when the model tried to confirm a booking without CRM success."""
    l = (lang or "ar").lower()
    if l == "en":
        return (
            "Your appointment is not saved in our system yet—the booking step did not complete successfully. "
            "Please do not consider it confirmed until the system confirms it; I will complete the booking next."
        )
    if l == "fr":
        return (
            "Votre rendez-vous n'est pas encore enregistré dans notre système — la réservation n'a pas abouti. "
            "Merci de ne pas le considérer comme confirmé tant que le système ne l'a pas validé."
        )
    return (
        "لم يُسجَّل الموعد بعد في نظام العيادة لأن خطوة الحجز لم تُكمَل بنجاح. "
        "من فضلك لا تعتبري الموعد مؤكداً قبل ما يظهر تأكيد من النظام—رح كمّل إجراء الحجز بالأدوات المناسبة."
    )


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
    # Franco-Arabic off-topic variants
    "dawle",
    "dawlat",
    "3alam",
    "ra2is",
    "siyase",
    "siyaseh",
    "wazir",
    "ekhtara3",
    "e5tr3",
    "invented",
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
    # Exclude ask_gender/initial_greet_and_ask_gender - send full AI reply (name + gender in one message)
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

GREETING_OPENERS = (
    "مرحبا",
    "مرحباً",
    "اهلا",
    "أهلا",
    "أهلاً",
    "هلا",
    "السلام عليكم",
    "صباح الخير",
    "مساء الخير",
    "hello",
    "hi",
    "good morning",
    "good evening",
    "bonjour",
    "salut",
    "bonsoir",
)

_GREETING_PREFIX_RE = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(opener) for opener in sorted(GREETING_OPENERS, key=len, reverse=True))
    + r")\b[\s،,:;!.\-–—]*",
    re.IGNORECASE,
)

_LEADING_ADDRESS_RE = re.compile(
    r"^\s*(?:أستاذ|استاذ|عزيزتي|حضرتك)\s+[^\s،,:;!?-]+(?:\s+[^\s،,:;!?-]+){0,2}\s*[،,:;!\-–—]*"
)

BOOKING_OFFER_QUESTION_RE = re.compile(
    r"(?:"
    r"هل\s*(?:ترغب|تحب|بدك).*(?:حجز|نحجز).*(?:موعد)"
    r"|(?:بدك|بتحب|تحب).*(?:نحجز|حجز).*(?:موعد)"
    r"|would\s+you\s+like.*(?:book|schedule).*(?:appointment)"
    r"|do\s+you\s+want.*(?:book|schedule).*(?:appointment)"
    r"|souhaitez[-\s]*vous.*(?:prendre|r[ée]server).*(?:rendez[-\s]*vous)"
    r"|voulez[-\s]*vous.*(?:prendre|r[ée]server).*(?:rendez[-\s]*vous)"
    r"|(?:bade|baddi|baddak|bet7eb|te7eb).*(?:hajz|ehjez|ehjoz|maw3ad)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

AFFIRMATIVE_CONFIRMATION_TOKENS = {
    "اه", "اي", "ايه", "نعم", "تمام", "اكيد", "أكيد",
    "yes", "yeah", "yep", "oui", "ok", "okay", "sure", "eh",
}
AFFIRMATIVE_CONFIRMATION_PHRASES = (
    "يا ريت",
    "أكيد بدي",
    "اكيد بدي",
    "yes please",
    "sure please",
)
NEGATIVE_CONFIRMATION_TOKENS = {"لا", "no", "non", "nope", "nah"}
NEGATIVE_CONFIRMATION_PHRASES = (
    "ما بدي",
    "مش ضروري",
    "لا شكرا",
    "لا شكرًا",
    "خليني معك",
    "no thanks",
    "non merci",
)
BOOKING_INTENT_CONFIRMATION_KEYWORDS = (
    "حجز",
    "احجز",
    "موعد",
    "book",
    "booking",
    "appointment",
    "rendez",
    "rdv",
    "hajz",
    "maw3ad",
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


def _is_plausible_extracted_customer_name(name: str, user_message: str) -> bool:
    """
    Reject GPT "detected_name" values that are really the user's message, booking text,
    or other non-name content (prevents wrong names in CRM / Activity Flow).
    """
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    msg = (user_message or "").strip()
    if len(n) < 2 or len(n) > 45:
        return False
    if any(ch.isdigit() for ch in n):
        return False
    words = n.split()
    if len(words) > 4:
        return False
    # Model echoed the entire user message as "name"
    if msg and n.lower() == msg.lower():
        return False
    if msg and len(msg) > 12:
        if n.lower() in msg.lower() and len(n) / max(len(msg), 1) > 0.72:
            return False
    nl = n.lower()
    for kw in (
        "se3a", "ساعة", "saat", "hour", "book", "حجز", "appointment", "موعد",
        "hotle", "hotel", "فندق", "coffee", "قهوة", "table", "room", "laser",
        "ليزر", "tattoo", "price", "سعر", "دكتور", "dr.", "clinic", "عيادة",
        "today", "tomorrow", "غدا", "بكرا",
    ):
        if kw in nl:
            return False
    return True


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


def _unwrap_embedded_json_reply(text: str) -> str:
    """
    Some model responses may accidentally place a full JSON object inside bot_reply.
    Unwrap nested {"action": "...", "bot_reply": "..."} layers so users only see text.
    """
    value = str(text or "").strip()
    for _ in range(3):
        if not value.startswith("{"):
            break
        try:
            parsed = json.loads(value)
        except Exception:
            break
        if not isinstance(parsed, dict) or "bot_reply" not in parsed:
            break
        value = str(parsed.get("bot_reply") or "").strip()
    return value


def _clean_reply_text(text: str) -> str:
    value = _unwrap_embedded_json_reply(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{2,}", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _tokenize_intent_words(text: str) -> set:
    normalized = _clean_reply_text(text).lower()
    return set(re.findall(r"[a-zA-Z0-9\u0600-\u06FF]+", normalized, re.UNICODE))


def _looks_like_booking_offer_confirmation_question(reply_text: str) -> bool:
    cleaned = _clean_reply_text(reply_text)
    if not cleaned or ("؟" not in cleaned and "?" not in cleaned):
        return False
    return bool(BOOKING_OFFER_QUESTION_RE.search(cleaned))


def _classify_booking_offer_confirmation_reply(user_text: str) -> str:
    normalized = _clean_reply_text(user_text).lower()
    if not normalized:
        return ""

    tokens = _tokenize_intent_words(normalized)

    if any(phrase in normalized for phrase in NEGATIVE_CONFIRMATION_PHRASES):
        return "no"
    if tokens.intersection(NEGATIVE_CONFIRMATION_TOKENS):
        return "no"

    if any(phrase in normalized for phrase in AFFIRMATIVE_CONFIRMATION_PHRASES):
        return "yes"
    if tokens.intersection(AFFIRMATIVE_CONFIRMATION_TOKENS):
        return "yes"
    if any(keyword in normalized for keyword in BOOKING_INTENT_CONFIRMATION_KEYWORDS):
        return "yes"

    return ""


def _build_booking_followup_question(lang: str) -> str:
    messages = {
        "ar": "أكيد، خلّينا نحجز موعد جديد. لأي خدمة بتحب تحجز؟",
        "franco": "أكيد، خلّينا نحجز موعد جديد. لأي خدمة بتحب تحجز؟",
        "en": "Sure, let's book a new appointment. Which service would you like to book?",
        "fr": "Bien sûr, prenons un nouveau rendez-vous. Pour quel service souhaitez-vous réserver ?",
    }
    return messages.get((lang or "ar").lower(), messages["ar"])


def _build_booking_decline_reply(lang: str) -> str:
    messages = {
        "ar": "تمام، ولا يهمك. إذا حبيت تحجز لاحقاً خبرني وأنا بساعدك فوراً.",
        "franco": "تمام، ولا يهمك. إذا حبيت تحجز لاحقاً خبرني وأنا بساعدك فوراً.",
        "en": "No problem at all. If you'd like to book later, let me know and I'll help right away.",
        "fr": "Pas de souci. Si vous souhaitez réserver plus tard, dites-le-moi et je vous aide tout de suite.",
    }
    return messages.get((lang or "ar").lower(), messages["ar"])


def _looks_like_greeting_unit(unit: str) -> bool:
    probe = _clean_reply_text(unit).lower()
    if not probe:
        return False
    return probe.startswith(GREETING_OPENERS)


def _strip_leading_greeting_phrase(text: str) -> str:
    cleaned = _clean_reply_text(text)
    if not cleaned:
        return cleaned

    without_greeting = _GREETING_PREFIX_RE.sub("", cleaned, count=1).strip()
    if without_greeting == cleaned:
        return cleaned

    without_address = _LEADING_ADDRESS_RE.sub("", without_greeting, count=1).strip()
    without_address = re.sub(r"^[،,:;!\-–—]+\s*", "", without_address).strip()
    return without_address or cleaned


def _strip_redundant_greeting_prefix(reply_text: str) -> str:
    """
    Remove a leading greeting sentence when the turn is not eligible for greeting.
    Keeps original order and only strips the first greeting-like unit when there is
    enough remaining content.
    """
    cleaned = _clean_reply_text(reply_text)
    units = _split_reply_units(cleaned)
    if units and _looks_like_greeting_unit(units[0]):
        first_unit_wo_greeting = _strip_leading_greeting_phrase(units[0])
        if first_unit_wo_greeting and first_unit_wo_greeting != units[0]:
            rebuilt = " ".join([first_unit_wo_greeting] + units[1:]).strip()
            if len(rebuilt) >= 20:
                return rebuilt

        if len(units) >= 2:
            remaining = " ".join(units[1:]).strip()
            if len(remaining) >= 20:
                return remaining

    fallback = _strip_leading_greeting_phrase(cleaned)
    if fallback != cleaned and len(fallback) >= 20:
        return fallback
    return cleaned


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

        first_info_index = next(
            (idx for idx, unit in enumerate(units) if not _looks_like_question(unit)),
            None,
        )

        # If everything looks like a question, keep the first one only.
        if first_info_index is None:
            return _truncate_chars(units[0], 220)

        info_unit = _truncate_chars(units[first_info_index], 180)

        # Prefer a follow-up question that appears AFTER the selected info sentence
        # so we preserve natural order and avoid reversed output.
        question_unit = next(
            (
                unit
                for idx, unit in enumerate(units)
                if idx > first_info_index and _looks_like_question(unit)
            ),
            "",
        )

        if question_unit:
            question_unit = _truncate_chars(question_unit, 140)
            combined = f"{info_unit} {question_unit}".strip()
            return _truncate_chars(combined, 320)

        # If no trailing question exists, allow a short leading greeting question (same order).
        leading_question = next(
            (
                unit
                for idx, unit in enumerate(units[:first_info_index])
                if _looks_like_question(unit)
            ),
            "",
        )
        if leading_question and first_info_index <= 1:
            combined = f"{_truncate_chars(leading_question, 140)} {info_unit}".strip()
            return _truncate_chars(combined, 320)

        return info_unit

    return cleaned


def _user_explicitly_requests_human_agent(text: str) -> bool:
    """True if the current user message clearly asks to speak with a person (not inferred from history)."""
    if not text or not str(text).strip():
        return False
    m = str(text).lower()
    needles = (
        "human",
        "agent",
        "person",
        "staff",
        "representative",
        "operator",
        "speak to",
        "talk to someone",
        "real person",
        "live agent",
        "customer service",
        "advisor",
        "supervisor",
        "موظف",
        "شخص",
        "بشري",
        "حد بشري",
        "خدمة العملاء",
        "بدي حدا",
        "بدي موظف",
        "بدي اتكلم",
        "مدير",
    )
    return any(n in m for n in needles)


async def _process_and_respond(user_id: str, user_name: str, user_input_to_process: str, user_data: dict, send_message_func, send_action_func, user_image_base64: str = None, user_image_format: str = "jpeg"):
    """
    Core logic for processing user input and generating bot response.
    This function is adapted from the original `_process_and_respond`
    but now works with WhatsApp IDs and sender functions.
    """
    from utils.utils import is_post_takeover_escalation_cooldown, set_post_takeover_escalation_cooldown

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

    # AI-PRIMARY: Bot passes message to AI as-is. AI extracts language, gender, name and returns them.
    # Bot saves what AI returns. No bot-side keyword/pattern extraction for name.

    # Check if human takeover is active (dashboard /api/test-* sets _dashboard_test_simulation to bypass and reach GPT)
    if not user_data.get("_dashboard_test_simulation") and config.user_in_human_takeover_mode.get(user_id, False):
        print(f"[_process_and_respond] INFO: Conversation {current_conversation_id} for user {user_id} is in human takeover mode. AI fallback guard active.")
        # IMPORTANT: During assigned operator takeover, AI must stay silent.
        # We only stay silent when an operator is assigned.
        # In all uncertain/error cases, prefer sending a waiting message instead of returning no response.
        should_send_waiting = True
        takeover_still_active = True
        try:
            db = get_firestore_db()
            if db:
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

                conv_id_to_check = current_conversation_id
                if not conv_id_to_check:
                    from utils.utils import _resolve_latest_conversation_id

                    user_doc_ref = users_coll.document(canonical_user_id)
                    conversations_collection_for_user = user_doc_ref.collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    )
                    conv_id_to_check = await _resolve_latest_conversation_id(conversations_collection_for_user)
                    if conv_id_to_check:
                        print(
                            f"[_process_and_respond] INFO: Using latest conversation {conv_id_to_check} "
                            f"for takeover sync (no current_conversation_id)"
                        )

                conv_data = None
                if conv_id_to_check:
                    for candidate_user_id in candidate_user_ids:
                        candidate_ref = users_coll.document(candidate_user_id).collection(
                            config.FIRESTORE_CONVERSATIONS_COLLECTION
                        ).document(conv_id_to_check)
                        candidate_snap = await asyncio.to_thread(candidate_ref.get)
                        if candidate_snap.exists:
                            conv_data = candidate_snap.to_dict() or {}
                            break

                if conv_data is None:
                    takeover_still_active = False
                    should_send_waiting = False
                    from utils.utils import _clear_takeover_flags_for_user

                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                    print(
                        f"[_process_and_respond] INFO: No Firestore conversation for takeover check; "
                        f"cleared stale takeover flag for {user_id}"
                    )
                elif conv_data.get("human_takeover_active", False):
                    should_send_waiting = True
                else:
                    takeover_still_active = False
                    should_send_waiting = False
                    from utils.utils import _clear_takeover_flags_for_user, sync_post_release_cooldown_from_conv_payload

                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                    sync_post_release_cooldown_from_conv_payload(user_data, conv_data)
                    user_data["just_returned_from_human_takeover"] = True
                    if not is_post_takeover_escalation_cooldown(user_data):
                        set_post_takeover_escalation_cooldown(user_data)
                    print(
                        f"[_process_and_respond] INFO: Firestore shows takeover inactive for {user_id}; "
                        f"resuming normal bot flow (just_returned)."
                    )
        except Exception as takeover_check_error:
            print(f"[_process_and_respond] ⚠️ Takeover fallback check failed: {takeover_check_error}")

        if takeover_still_active and should_send_waiting:
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
    # Skip for images – they are always in scope (tattoo analysis).
    if not user_image_base64 and _is_out_of_clinic_scope_query(user_input_to_process):
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
    # Long one-line messages often include gender («ana shab», «شاب», etc.). Infer before router/GPT
    # so runtime context and router do not ask again. Full user_input_to_process is still sent to GPT unchanged.
    if current_gender == "unknown" and (user_input_to_process or "").strip():
        _ginf = get_gender_from_message(user_input_to_process)
        if _ginf in ("male", "female"):
            config.user_gender[user_id] = _ginf
            current_gender = _ginf
            if config.user_greeting_stage.get(user_id, 0) < 2:
                config.user_greeting_stage[user_id] = 2
            try:
                await user_persistence.save_user_gender(
                    user_id,
                    _ginf,
                    phone=user_data.get("phone_number", user_id),
                    name=user_name,
                )
            except Exception as _ge:
                print(f"⚠️ save_user_gender (pre-router infer): {_ge}")
            print(f"[_process_and_respond] ✅ Gender inferred from full message (pre-router): {_ginf}")

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
        async def _activate_ai_handover_router(escalation_reason: str, trigger_source: str) -> bool:
            from utils.utils import (
                conversation_any_path_post_release_blocked,
                merge_conversation_user_id_variants,
                update_conversation_on_all_existing_paths,
            )

            wrote = False
            db = get_firestore_db()
            if db and current_conversation_id:
                try:
                    if await conversation_any_path_post_release_blocked(current_conversation_id, user_id):
                        print("⚠️ router handover blocked: post-release cooldown on at least one path")
                        return False
                    payload = {
                        "status": "waiting_human",
                        "human_takeover_active": True,
                        "human_takeover_requested": True,
                        "operator_id": None,
                        "conversation_state": "waiting_for_operator",
                        "escalation_reason": escalation_reason,
                        "escalation_time": datetime.datetime.now(),
                        "last_updated": datetime.datetime.now(),
                        "post_release_escalation_suppressed_until": None,
                    }
                    n = await update_conversation_on_all_existing_paths(
                        current_conversation_id, user_id, payload
                    )
                    if n > 0:
                        wrote = True
                except Exception as e:
                    print(f"⚠️ Failed to update handover state: {e}")
            if not wrote:
                return False
            for vid in merge_conversation_user_id_variants("", user_id):
                config.user_in_human_takeover_mode[vid] = True
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
            return True

        router_handover_ok = await _activate_ai_handover_router("customer_requested_human", "router_human_handover")
        if router_handover_ok:
            handoff_msg = {"ar": "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏", "en": "Thanks for your patience. You'll be transferred to one of our staff members shortly. 🙏", "fr": "Merci pour votre patience. Vous serez transféré à l'un de nos employés sous peu. 🙏"}
            sent_reply = handoff_msg.get(current_preferred_lang, handoff_msg["ar"])
            await send_message_func(user_id, sent_reply)
            await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
            log_report_event("human_handover", user_id, current_gender, {"message": user_input_to_process, "status": "router_direct", "source": "router"})
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        else:
            fb = get_dynamic_message("generic_error_message", current_preferred_lang) or "كيف فيني ساعدك؟"
            await send_message_func(user_id, fb)
            await save_conversation_message_to_firestore(user_id, "ai", fb, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
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
    awaiting_booking_offer_confirmation = bool(user_data.get("awaiting_booking_offer_confirmation", False))

    gpt_response_data = {}
    query_pre_set_from_booking_confirmation = False

    if awaiting_booking_offer_confirmation:
        booking_confirmation = _classify_booking_offer_confirmation_reply(user_input_to_process)
        if booking_confirmation == "yes":
            booking_origin_query = (
                user_data.get("booking_offer_origin_query")
                or user_data.get("original_question")
                or user_data.get("pending_clarification_query")
                or "new_booking_request"
            )
            user_data["original_question"] = booking_origin_query
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None
            # Pass to GPT with full context – user already discussed service/branch (e.g. tattoo removal Beirut).
            # Do NOT overwrite with "لأي خدمة بتحب تحجز؟" – GPT will use discussed service + user's date/time.
            query_to_send_to_gpt = (
                f"[User confirmed booking. Previously discussed: {booking_origin_query}. User reply: {user_input_to_process}]"
            )
            query_pre_set_from_booking_confirmation = True
            # Do NOT set gpt_response_data – let GPT proceed with submit_booking_intent (or tools) using context.
        elif booking_confirmation == "no":
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None
            gpt_response_data = {
                "action": "answer_question",
                "bot_reply": _build_booking_decline_reply(current_preferred_lang),
                "detected_language": current_preferred_lang,
                "detected_gender": current_gender if current_gender != "unknown" else None,
                "current_gender_from_config": current_gender,
            }
        else:
            # Treat unresolved short acknowledgments as stale and continue normal flow.
            user_data["awaiting_booking_offer_confirmation"] = False
            user_data["booking_offer_origin_query"] = None

    # AI interprets yes/no for handover confirmation - no bot-side keyword matching
    if not gpt_response_data and awaiting_confirmation:
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
        conversation_history = await get_conversation_context_for_gpt(
            user_id,
            current_conversation_id,
            window_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
            alternate_user_id=canonical_user_id,
        )
        last_ai_response_at = await get_conversation_last_ai_response_at(user_id, current_conversation_id, canonical_user_id) if current_conversation_id else None
        gpt_response_data = await get_bot_chat_response(
            user_id=user_id,
            user_input=user_input_to_process,
            current_context_messages=conversation_history,
            current_gender=current_gender,
            current_preferred_lang=current_preferred_lang,
            response_language=response_language,
            is_initial_message_after_start=is_initial_message_for_gpt,
            initial_user_query_to_process=initial_user_query_to_process_original,
            last_ai_response_at=last_ai_response_at,
        )

    # Must be `if`, not `elif`: if the handover-confirmation GPT call above returns a falsy/empty
    # payload, we still need the FAQ + main GPT path. `elif` would skip it and leave gpt_response_data empty.
    if not gpt_response_data:
        # Only use raw input when not resuming; do NOT overwrite query pre-set from booking confirmation
        if not _resume_original_question and not query_pre_set_from_booking_confirmation:
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
            qa_response = _apply_turn_by_turn_policy(
                "answer_question",
                qa_response,
                current_preferred_lang,
            )
            if not (qa_response or "").strip():
                qa_response = (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، إجابة قاعدة الأسئلة كانت فارغة. جرّب إعادة صياغة السؤال."
                )
                print("[_process_and_respond] WARN: Q&A match had empty answer after policy → generic fallback")

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
            qa_steps = [
                {"step": 1, "title": "User → Bot", "content": query_to_send_to_gpt},
                {"step": 2, "title": flow_match_title, "content": f"Bot matched from Q&A database. Score: {match_score:.0%}. No AI call."},
                {"step": 3, "title": "Bot → User", "content": qa_response, "event_type": "response_sent"},
            ]
            voice_meta = user_data.pop("_voice_flow_meta", None)
            if voice_meta:
                qa_steps = [
                    {"step": 1, "title": "Voice received", "content": "User sent voice message.", "event_type": "voice_received", "status": "success", "message_type": "voice"},
                    {"step": 2, "title": "Transcription completed", "content": f"Result: {voice_meta.get('transcription_length', 0)} chars. Model: {voice_meta.get('transcription_model', 'gpt-4o-transcribe')}.", "event_type": "transcription_completed", "status": "success", "duration_ms": voice_meta.get("transcription_duration_ms")},
                    {"step": 3, "title": "User → Bot", "content": query_to_send_to_gpt},
                    {"step": 4, "title": flow_match_title, "content": f"Bot matched from Q&A database. Score: {match_score:.0%}. No AI call."},
                    {"step": 5, "title": "Bot → User", "content": qa_response, "event_type": "response_sent"},
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
                flow_steps=qa_steps,
                message_type="voice" if voice_meta else "text",
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

            # Fetch conversation history once (same 12h window as normal context) – use for selector and for GPT.
            canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
            conversation_history = await get_conversation_context_for_gpt(
                user_id,
                current_conversation_id,
                window_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
                alternate_user_id=canonical_user_id,
            )
            last_ai_response_at = await get_conversation_last_ai_response_at(user_id, current_conversation_id, canonical_user_id) if current_conversation_id else None
            last_bot_msg = await get_last_bot_message_for_gpt_context(
                user_id,
                current_conversation_id,
                canonical_user_id,
                within_hours=getattr(config, "CONTEXT_WINDOW_HOURS", 12),
            )

            if last_bot_msg and query_to_send_to_gpt:
                try:
                    _meta = last_bot_msg.get("metadata") or {}
                    if _meta.get("source") == "smart_message" and _meta.get("type") == "reminder_24h":
                        from utils.reminder_analytics import classify_reminder_reply_intent

                        _rint = classify_reminder_reply_intent(query_to_send_to_gpt)
                        if _rint:
                            _pn = user_data.get("phone_number")
                            analytics.log_smart_reminder_reply(
                                user_id=user_id,
                                intent=_rint,
                                source_message_id=_meta.get("message_id"),
                                appointment_id=_meta.get("appointment_id"),
                                phone=str(_pn).strip() if _pn else None,
                            )
                except Exception as _ra:
                    print(f"[_process_and_respond] reminder reply analytics: {_ra}")

            # ALWAYS run selector: pass query + context_messages so selector understands what the conversation is about (e.g. user "eh" / "beirut" after we asked branch).
            from services.dynamic_retrieval_service import (
                retrieve_and_merge,
                is_dynamic_retrieval_available,
            )
            custom_context = None
            _dynamic_retrieval_flow_meta = None
            selector_query = query_to_send_to_gpt
            if user_image_base64:
                selector_query = (
                    "The user sent an image (attached below). Examine the image and the conversation context. "
                    "Select which files to load. Do not assume – pick based on what you observe."
                )
            if is_dynamic_retrieval_available():
                merged, _clar, _act, _dynamic_retrieval_flow_meta = await retrieve_and_merge(
                    selector_query,
                    include_price_hint=is_price_intent,
                    response_lang=current_preferred_lang,
                    context_messages=conversation_history,
                    user_image_base64=user_image_base64,
                    user_image_format=user_image_format,
                )
                custom_context = merged if merged else None
                print(f"[_process_and_respond] ✅ Selector ran: action={_act}, context_len={len(custom_context or '')}")

            # Phase 3: Build operational context when resuming (Plan §10)
            operational_context = None
            if user_data.pop('just_returned_from_human_takeover', False):
                takeover_ctx = (
                    "**USER JUST RETURNED FROM HUMAN TAKEOVER (CRITICAL):**\n"
                    "- A human operator just finished with this user. The conversation was released back to the bot.\n"
                    "- **Conversation history sent to you may omit messages from before the release** (technical reset for a clean AI session).\n"
                    "- Do NOT re-escalate to human based on OLD frustration or complaints that are no longer in the history.\n"
                    "- Only hand over if the user EXPLICITLY asks for a human in THIS current message.\n"
                    "- Treat this as a fresh start. Answer their current question normally."
                )
                operational_context = (operational_context + "\n\n" + takeover_ctx) if operational_context else takeover_ctx
            if _resume_original_question:
                orig_q = user_data.get('original_question') or conv_state.get('original_question')
                ctx = (
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
                operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx
            # When last message was from us (e.g. smart message, notification): give GPT context so it doesn't lose domain
            if last_bot_msg and last_bot_msg.get("text"):
                last_text = (last_bot_msg.get("text") or "")[:500]
                is_smart = (last_bot_msg.get("metadata") or {}).get("source") == "smart_message"
                ctx = (
                    f"Last message we sent to the user: \"{last_text}\"\n"
                    f"Domain: clinic (ليناز ليزر). "
                )
                if is_smart:
                    ctx += "This was a clinic notification. The user might be replying to or asking about it. "
                ctx += "Do not lose context – the user might be talking or asking about this."
                operational_context = (operational_context + "\n\n" + ctx) if operational_context else ctx

            if is_post_takeover_escalation_cooldown(user_data):
                cooldown_ctx = (
                    "**POST-RELEASE COOLDOWN (CRITICAL):** This user was recently returned to the bot from human support.\n"
                    "- Do NOT set handover_degree to medium or high based on old messages or past frustration.\n"
                    "- Do NOT choose action human_handover unless they clearly ask to speak to a person **in this message**.\n"
                    "- Answer their current message normally; ignore stale anger/complaints in history for escalation."
                )
                operational_context = (operational_context + "\n\n" + cooldown_ctx) if operational_context else cooldown_ctx

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
                last_ai_response_at=last_ai_response_at,
                user_image_base64=user_image_base64,
                user_image_format=user_image_format,
            )

    if not gpt_response_data:
        print("[_process_and_respond] ERROR: gpt_response_data is empty — synthesizing fallback reply")
        gpt_response_data = {
            "action": "answer_question",
            "bot_reply": (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "عذراً، ما قدرت أكمل المعالجة. جرّب مرة ثانية أو تواصل معنا مباشرة."
            ),
            "detected_language": current_preferred_lang,
            "current_gender_from_config": current_gender,
            "_flow_meta": {"error": "empty_gpt_response_payload"},
        }

    action = gpt_response_data.get("action")
    bot_reply_text = gpt_response_data.get("bot_reply")
    handover_degree = str(gpt_response_data.get("handover_degree") or "none").strip().lower()
    _flow_error_reason = None  # For Activity Flow: which step failed
    detected_gender_from_gpt = gpt_response_data.get("detected_gender")
    detected_language = gpt_response_data.get("detected_language")
    detected_name_from_gpt = gpt_response_data.get("detected_name")
    escalation_reason_from_gpt = gpt_response_data.get("escalation_reason")
    flow_meta = gpt_response_data.get("_flow_meta") or {}

    # When GPT fails (error in flow_meta): if user in waiting queue → waiting message; else → hand over to human
    if flow_meta.get("error"):
        in_waiting = config.user_in_human_takeover_mode.get(user_id, False)
        if not in_waiting and current_conversation_id:
            try:
                db = get_firestore_db()
                if db:
                    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                    users_coll = db.collection("artifacts").document("linas-ai-bot-backend").collection("users")
                    for uid in [canonical_user_id, user_id]:
                        if not uid:
                            continue
                        ref = users_coll.document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
                        snap = await asyncio.to_thread(ref.get)
                        if snap.exists:
                            d = snap.to_dict() or {}
                            if d.get("human_takeover_active") and not d.get("operator_id"):
                                in_waiting = True
                            break
            except Exception as e:
                print(f"[_process_and_respond] ⚠️ Waiting-check on error failed: {e}")
        if in_waiting:
            bot_reply_text = get_dynamic_message("waiting_queue_message", current_preferred_lang) or "شوي، منكون معك، شكراً لصبركم، عندنا شوي ضغط 🙏"
            action = "answer_question"
            print(f"[_process_and_respond] GPT error but user {user_id} in waiting queue → sending waiting message")
        else:
            if is_post_takeover_escalation_cooldown(user_data):
                bot_reply_text = (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، واجهت مشكلة تقنية لحظية. جرّب إعادة صياغة سؤالك أو انتظر لحظة ثم أعد المحاولة."
                )
                action = "answer_question"
                print(
                    f"[_process_and_respond] GPT/system error during post-release cooldown → generic reply, no handover. error={flow_meta.get('error')}"
                )
            else:
                # Error/API/system issue → hand over to human
                action = "human_handover"
                escalation_reason_from_gpt = "technical_error"
                print(f"[_process_and_respond] GPT/system error → handing over to human. error={flow_meta.get('error')}")

    # AI-assessed handover degree: if GPT says medium/high, override to human_handover
    if (
        handover_degree in ("medium", "high")
        and action not in ("human_handover", "human_handover_confirmed", "human_handover_initial_ask")
        and not is_post_takeover_escalation_cooldown(user_data)
    ):
        print(f"[_process_and_respond] 🔄 handover_degree={handover_degree} → overriding action to human_handover")
        action = "human_handover"
        escalation_reason_from_gpt = escalation_reason_from_gpt or "frustration_detected"
    elif handover_degree in ("medium", "high") and is_post_takeover_escalation_cooldown(user_data):
        print(
            f"[_process_and_respond] post-release cooldown: ignoring handover_degree={handover_degree} (keeping action={action})"
        )

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
    action_was_coerced = False
    if action not in known_actions:
        if bot_reply_text:
            print(
                f"[_process_and_respond] ⚠️ Unexpected GPT action '{action}'. "
                "Using 'answer_question' since bot_reply is present."
            )
            action = "answer_question"
            action_was_coerced = True
        else:
            bad_action = action
            if is_post_takeover_escalation_cooldown(user_data):
                action = "answer_question"
                bot_reply_text = (
                    get_dynamic_message("generic_error_message", current_preferred_lang)
                    or "عذراً، لم أتمكن من معالجة طلبك الآن. حاول مرة أخرى بصياغة أبسط."
                )
                print(
                    f"[_process_and_respond] WARN: bad GPT action '{bad_action}' during cooldown → generic reply, no handover"
                )
            else:
                action = "human_handover"
                escalation_reason_from_gpt = "technical_error"
                _flow_error_reason = f"Step: Parse GPT response | Action '{bad_action}' not in known_actions, bot_reply empty. flow_meta.error={flow_meta.get('error', 'none')}"
                print(f"[_process_and_respond] WARN: GPT action '{bad_action}' not in known_actions and bot_reply empty → handing over to human. flow_error={flow_meta.get('error', 'none')}")

    # AI-PRIMARY: No bot-side overrides. Send AI reply as-is.

    # If we had to coerce an invalid action from GPT, keep the full AI wording
    # instead of compressing it into the brief turn-by-turn format.
    if action_was_coerced:
        bot_reply_text = _clean_reply_text(bot_reply_text)
    # AI-PRIMARY: No turn-by-turn truncation or greeting strip. Send AI reply as-is.

    # Never allow a CRM-style confirmation unless this turn actually received booked=true from the booking tool.
    if action == "confirm_booking_details" and not _flow_meta_has_crm_booking_confirmation(flow_meta):
        print(
            "[_process_and_respond] BLOCKED confirm_booking_details: no submit_booking_intent/create_appointment "
            "with success+booking_flow_state=booked in tool_round_trips"
        )
        action = "answer_question"
        bot_reply_text = _booking_not_confirmed_safe_reply(current_preferred_lang)

    if (
        is_post_takeover_escalation_cooldown(user_data)
        and action == "human_handover"
        and bot_reply_text
        and not _user_explicitly_requests_human_agent(user_input_to_process)
    ):
        print(
            "[_process_and_respond] post-release cooldown: AI chose human_handover without explicit user request → answer_question"
        )
        action = "answer_question"

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

    async def _activate_ai_handover(escalation_reason: str, trigger_source: str) -> bool:
        """Switch conversation to waiting_human, notify admins. Returns True if Firestore was updated."""
        from utils.utils import (
            conversation_any_path_post_release_blocked,
            merge_conversation_user_id_variants,
            update_conversation_on_all_existing_paths,
        )

        wrote = False
        db = get_firestore_db()
        if db and current_conversation_id:
            try:
                canonical_user_id, _ = get_canonical_user_id_and_phone(user_id, user_data.get("phone_number"))
                update_payload = {
                    "status": "waiting_human",
                    "human_takeover_active": True,
                    "human_takeover_requested": True,
                    "operator_id": None,
                    "conversation_state": "waiting_for_operator",
                    "escalation_reason": escalation_reason,
                    "escalation_time": datetime.datetime.now(),
                    "last_updated": datetime.datetime.now(),
                    "post_release_escalation_suppressed_until": None,
                }
                # User explicitly confirmed transfer — allow even during cooldown
                if trigger_source not in ("ai_handover_confirmed",):
                    if await conversation_any_path_post_release_blocked(current_conversation_id, user_id):
                        print(
                            f"⚠️ _activate_ai_handover skipped: post-release cooldown (trigger={trigger_source}) conv={current_conversation_id}"
                        )
                        return False
                n = await update_conversation_on_all_existing_paths(
                    current_conversation_id, user_id, update_payload
                )
                if n == 0:
                    print(
                        f"⚠️ Conversation {current_conversation_id} not found in Firestore on any user path"
                    )
                else:
                    wrote = True
                    print(
                        f"✅ Conversation {current_conversation_id} set to waiting_human (AI decision, {n} path(s))"
                    )
                    try:
                        from services.live_chat_service import live_chat_service
                        live_chat_service.invalidate_cache()
                        await live_chat_service._refresh_index_for_conversation(
                            canonical_user_id, current_conversation_id
                        )
                    except Exception as idx_err:
                        print(f"⚠️ Index refresh after AI handover: {idx_err}")
            except Exception as e:
                print(f"⚠️ Failed to update handover state in Firestore: {e}")

        if not wrote:
            return False

        for vid in merge_conversation_user_id_variants("", user_id):
            config.user_in_human_takeover_mode[vid] = True

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
        return True

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

    # Save detected_name from AI (AI-primary: AI extracts, bot saves)
    if detected_name_from_gpt and isinstance(detected_name_from_gpt, str):
        name_clean = detected_name_from_gpt.strip()
        name_pattern = r"^[A-Za-z\u00C0-\u00FF\u0600-\u06FF\s\-\']+$"
        if (
            2 <= len(name_clean) <= 50
            and re.match(name_pattern, name_clean, re.UNICODE)
            and _is_plausible_extracted_customer_name(name_clean, user_input_to_process)
        ):
            config.user_names[user_id] = name_clean
            user_data["collected_name"] = name_clean
            user_data["name_source"] = "ai_extracted"
            user_data["awaiting_name_input"] = False
            config.user_greeting_stage[user_id] = 2
            db = get_firestore_db()
            if db:
                try:
                    app_id_for_firestore = "linas-ai-bot-backend"
                    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)
                    user_doc_ref.update({"name": name_clean, "last_updated": datetime.datetime.now()})
                except Exception as e:
                    print(f"⚠️ Failed to save name to Firestore: {e}")
            log_report_event("name_saved", name_clean, current_gender, {"method": "AI Extraction", "whatsapp_id": user_id})
            print(f"✅ Saved name '{name_clean}' from AI for user {user_id}")
            user_name = name_clean
        elif 2 <= len(name_clean) <= 50 and re.match(name_pattern, name_clean, re.UNICODE):
            print(
                f"⚠️ Rejected AI extracted name (not plausible vs message): "
                f"'{name_clean[:80]}' | message_len={len(user_input_to_process or '')}"
            )

    if detected_gender_from_gpt and config.user_gender.get(user_id) != detected_gender_from_gpt:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "User Input Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=config.user_names.get(user_id, user_name))
    elif detected_gender_from_gpt and config.user_gender.get(user_id) == "unknown" and detected_gender_from_gpt in ["male", "female"]:
        config.user_gender[user_id] = detected_gender_from_gpt
        log_report_event("gender_updated", user_name, detected_gender_from_gpt, {"method": "GPT Detection"})
        config.gender_attempts[user_id] = 0
        config.user_greeting_stage[user_id] = 2
        await user_persistence.save_user_gender(user_id, detected_gender_from_gpt, phone=user_id, name=config.user_names.get(user_id, user_name))

    # Dashboard test capture skips falsy message_text; WhatsApp should not receive empty bodies.
    _actions_requiring_bot_text = {
        "initial_greet_and_ask_gender",
        "ask_gender",
        "confirm_gender",
        "confirm_booking_details",
        "human_handover_initial_ask",
        "return_to_normal_chat",
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
    if action in _actions_requiring_bot_text and not (bot_reply_text or "").strip():
        bot_reply_text = (
            get_dynamic_message("generic_error_message", current_preferred_lang)
            or "عذراً، لم أتمكن من توليد رد الآن. حاول مرة أخرى."
        )
        print(
            f"[_process_and_respond] WARN: Empty bot_reply for action={action} → generic fallback "
            f"(flow_meta.error={flow_meta.get('error')!r})"
        )

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
        user_data['awaiting_human_handover_confirmation'] = False
        handover_ok = await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "customer_requested_human",
            trigger_source="ai_handover_confirmed"
        )
        if handover_ok:
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
        else:
            fallback = (bot_reply_text or "").strip() or (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "تمام، كيف فيني ساعدك بهاللحظة؟"
            )
            sent_reply = fallback
            await send_message_func(user_id, fallback)
            await save_conversation_message_to_firestore(user_id, "ai", fallback, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action == "return_to_normal_chat":
        user_data['awaiting_human_handover_confirmation'] = False
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action == "human_handover":
        handover_ok = await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "ai_decided_handoff",
            trigger_source="ai_handover_direct"
        )
        if handover_ok:
            handoff_msg = get_dynamic_message("human_handover_message", current_preferred_lang) or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
            sent_reply = handoff_msg
            await send_message_func(user_id, handoff_msg)
            await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
            log_report_event("human_handover", user_id, current_gender, {
                "message": user_input_to_process,
                "status": "direct",
                "source": "ai_handover_direct"
            })
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        else:
            fallback = (bot_reply_text or "").strip() or (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "كيف فيني ساعدك بهاللحظة؟"
            )
            sent_reply = fallback
            await send_message_func(user_id, fallback)
            await save_conversation_message_to_firestore(user_id, "ai", fallback, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    elif action in ["ask_for_details_for_booking", "ask_for_service_type", "ask_for_details", "ask_for_tattoo_photo", "ask_clarification"]:
        # Clarification anchor should point to the question being clarified now.
        # If we're already awaiting clarification, keep the existing anchor.
        clarification_anchor = user_data.get('pending_clarification_query') if user_data.get('awaiting_clarification') else None
        if not clarification_anchor:
            clarification_anchor = user_data.get('original_question') or user_input_to_process
        user_data['original_question'] = clarification_anchor
        user_data['awaiting_clarification'] = True
        user_data['last_bot_question_type'] = 'clarification'
        user_data['pending_clarification_query'] = clarification_anchor
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        config.user_greeting_stage[user_id] = 2

    elif action in ["content_moderated", "rate_limit_exceeded"]:
        # Moderation or rate limit: send the safe/limit message from the service (no GPT call).
        user_data['awaiting_gender'] = False
        user_data['awaiting_clarification'] = False
        user_data['pending_clarification_query'] = None
        reply_to_send = (bot_reply_text or "").strip() or (
            get_dynamic_message("generic_error_message", current_preferred_lang)
            or "عذراً، واجهت مشكلة في فهم طلبك حالياً. الرجاء المحاولة مرة أخرى."
        )
        sent_reply = reply_to_send
        await send_message_func(user_id, reply_to_send)
        await save_conversation_message_to_firestore(user_id, "ai", reply_to_send, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai", "action": action})
        config.user_greeting_stage[user_id] = 2

    elif action in ["answer_question", "normal_chat", "unknown_query", "provide_info", "tool_call", "check_customer_status", "confirm_appointment_reschedule"]:
        user_data['awaiting_gender'] = False
        user_data['awaiting_clarification'] = False
        user_data['pending_clarification_query'] = None
        # Clear stale carry-over so the next user intent starts fresh.
        user_data['original_question'] = None
        user_data['initial_user_query_to_process'] = None
        user_data['last_bot_question_type'] = None
        await send_message_func(user_id, bot_reply_text)
        await save_conversation_message_to_firestore(user_id, "ai", bot_reply_text, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
        config.user_greeting_stage[user_id] = 2

    else:
        # Unexpected action → hand over to human instead of generic error
        _flow_error_reason = f"Step: Bot → User | Unexpected action: '{action}'"
        print(f"[_process_and_respond] ERROR: Unexpected action '{action}' → handing over to human. bot_reply_len={len(bot_reply_text or '')} | flow_error={flow_meta.get('error', 'none')}")
        handover_ok = await _activate_ai_handover(
            escalation_reason=escalation_reason_from_gpt or "technical_error",
            trigger_source="unexpected_action"
        )
        if handover_ok:
            handoff_msg = get_dynamic_message("human_handover_message", current_preferred_lang) or "تم تحويلك لأحد من موظفينا شوي، ويكون معك. شكراً لصبرك 🙏"
            sent_reply = handoff_msg
            await send_message_func(user_id, handoff_msg)
            await save_conversation_message_to_firestore(user_id, "ai", sent_reply, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})
            log_report_event("human_handover", user_id, current_gender, {
                "message": user_input_to_process,
                "status": "direct",
                "source": "unexpected_action"
            })
            await update_dashboard_metric_in_firestore(user_id, "human_handover_requests", 1)
        else:
            fallback = (bot_reply_text or "").strip() or (
                get_dynamic_message("generic_error_message", current_preferred_lang)
                or "عذراً، صار خطأ بسيط. جرّب توضّح طلبك مرة ثانية."
            )
            sent_reply = fallback
            await send_message_func(user_id, fallback)
            await save_conversation_message_to_firestore(user_id, "ai", fallback, current_conversation_id, user_name, user_data.get('phone_number'), metadata={"handled_by": "ai"})

    # Keep yes/no booking-follow-up state when we explicitly ask:
    # "Would you like to book a new appointment?"
    if _looks_like_booking_offer_confirmation_question(sent_reply):
        booking_origin_query = (
            user_data.get("original_question")
            or user_data.get("pending_clarification_query")
            or user_input_to_process
        )
        user_data["awaiting_booking_offer_confirmation"] = True
        user_data["booking_offer_origin_query"] = booking_origin_query
        user_data["last_bot_question_type"] = "booking_offer_confirmation"
    else:
        user_data["awaiting_booking_offer_confirmation"] = False
        user_data["booking_offer_origin_query"] = None
        if user_data.get("last_bot_question_type") == "booking_offer_confirmation":
            user_data["last_bot_question_type"] = None

    # Flow logging for dashboard transparency
    response_time_ms = (time.time() - start_time) * 1000
    flow_source = "rate_limit" if action == "rate_limit_exceeded" else "moderation" if action == "content_moderated" else "gpt"
    flow_steps = None
    msg_type = "text"

    # Build multimodal prepended steps for Activity Flow
    def _prepend_multimodal_steps(steps_list, step_start: int) -> tuple:
        prepended = []
        offset = 0
        voice_meta = user_data.pop("_voice_flow_meta", None)
        if voice_meta:
            prepended.extend([
                {"step": step_start, "title": "Voice received", "content": "User sent voice message.", "event_type": "voice_received", "status": "success", "message_type": "voice"},
                {"step": step_start + 1, "title": "Voice downloaded/prepared", "content": f"Audio converted to MP3. Duration: {voice_meta.get('audio_duration_seconds', 0):.2f}s.", "event_type": "voice_downloaded", "status": "success", "message_type": "voice"},
                {"step": step_start + 2, "title": "Transcription started", "content": f"Sent to {voice_meta.get('transcription_model', 'gpt-4o-transcribe')}.", "event_type": "transcription_started", "model": voice_meta.get("transcription_model"), "message_type": "voice"},
                {"step": step_start + 3, "title": "Transcription completed", "content": f"Result: {voice_meta.get('transcription_length', 0)} chars in {voice_meta.get('transcription_duration_ms', 0):.0f}ms.", "event_type": "transcription_completed", "status": voice_meta.get("status", "success"), "duration_ms": voice_meta.get("transcription_duration_ms"), "message_type": "voice"},
            ])
            offset = 4
        if user_image_base64:
            prepended.extend([
                {"step": step_start + offset, "title": "Image received", "content": "User sent image.", "event_type": "image_received", "status": "success", "message_type": "image"},
                {"step": step_start + offset + 1, "title": "Image prepared", "content": f"Extracted base64, format: {user_image_format}.", "event_type": "image_prepared", "status": "success", "metadata": {"image_format": user_image_format}, "message_type": "image"},
            ])
            offset += 2
        for s in steps_list:
            s["step"] = s["step"] + offset
        return prepended + steps_list, "voice" if voice_meta else ("image" if user_image_base64 else "text")

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
        from services.dynamic_retrieval_service import (
            SELECTOR_MODEL,
            SELECTOR_MODEL_INPUT_PER_1M_USD,
            SELECTOR_MODEL_OUTPUT_PER_1M_USD,
        )

        sel_pt = dr.get("selector_prompt_tokens") or 0
        sel_ct = dr.get("selector_completion_tokens") or 0
        pt = flow_meta.get("prompt_tokens")
        ct = flow_meta.get("completion_tokens")
        main_model = flow_meta.get("model") or "gpt-5.1"
        main_cost = flow_meta.get("cost_usd") or 0.0
        selector_cost = (sel_pt / 1_000_000 * SELECTOR_MODEL_INPUT_PER_1M_USD) + (
            sel_ct / 1_000_000 * SELECTOR_MODEL_OUTPUT_PER_1M_USD
        )
        steps = [
            {"step": 1, "title": "User → Bot", "content": user_input_to_process, "tokens": 0, "model": None, "cost_usd": None},
            {"step": 2, "title": "Bot → AI (Selector)", "content": bot_sent_selector or "User message + file titles.", "tokens": sel_pt, "model": SELECTOR_MODEL, "cost_usd": round((sel_pt / 1_000_000 * SELECTOR_MODEL_INPUT_PER_1M_USD), 6) if sel_pt else None, "event_type": "selector_started"},
            {"step": 3, "title": "AI → Bot (Selector)", "content": ai_selected_str or "AI returned.", "tokens": sel_ct, "model": SELECTOR_MODEL, "cost_usd": round((sel_ct / 1_000_000 * SELECTOR_MODEL_OUTPUT_PER_1M_USD), 6) if sel_ct else None, "event_type": "selector_completed", "metadata": {"selected_files": selected_titles, "selected_count": len(selected_titles)}},
            {"step": 4, "title": "Bot loaded content", "content": loaded_content_block, "tokens": 0, "model": None, "cost_usd": None, "event_type": "retrieval_completed"},
        ]
        cust_ctx = flow_meta.get("customer_context_sent")
        if cust_ctx:
            steps.append({"step": 5, "title": "Bot → AI (Customer context)", "content": cust_ctx, "tokens": 0, "model": None, "cost_usd": None, "event_type": "customer_context_sent"})
        steps.append({"step": len(steps) + 1, "title": "Bot → AI (GPT)", "content": flow_meta.get("bot_sent_to_ai") or flow_meta.get("ai_query_summary") or "Merged content + user query sent to GPT.", "tokens": pt, "model": main_model, "cost_usd": round(flow_meta.get("input_cost_usd") or 0, 6) if (flow_meta.get("input_cost_usd") is not None) else None, "event_type": "main_ai_started"})
        step_num = len(steps) + 1
        if tool_round_trips:
            steps.append({"step": step_num, "title": "AI → Bot (requested tools)", "content": ai_first or "AI requested tool calls.", "tokens": 0, "model": None, "cost_usd": None})
            step_num += 1
            for tr in tool_round_trips:
                steps.append({"step": step_num, "title": f"AI requested: {tr.get('ai_requested', '?')}", "content": f"Args: {tr.get('args', '{}')}", "tokens": 0, "model": None, "cost_usd": None})
                step_num += 1
                exec_step = {
                    "step": step_num,
                    "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})",
                    "content": tr.get("bot_returned", ""),
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
                if tr.get("backend_execution"):
                    exec_step["metadata"] = {"backend_execution": tr["backend_execution"]}
                steps.append(exec_step)
                step_num += 1
            steps.append({"step": step_num, "title": "AI → Bot (GPT final)", "content": ai_raw_or_error or "(no content)", "tokens": ct, "model": main_model, "cost_usd": round(flow_meta.get("output_cost_usd") or 0, 6) if (flow_meta.get("output_cost_usd") is not None) else None, "event_type": "main_ai_completed"})
            step_num += 1
        else:
            steps.append({"step": step_num, "title": "AI → Bot (GPT)", "content": ai_raw_or_error or f"GPT returned. Model: {main_model} | Tokens: {(pt or 0) + (ct or 0)} | Time: {response_time_ms:.0f}ms", "tokens": ct, "model": main_model, "cost_usd": round(main_cost, 6) if main_cost else None, "event_type": "main_ai_completed"})
            step_num += 1
        if flow_meta.get("error") or _flow_error_reason:
            err_msg = flow_meta.get("error") or _flow_error_reason or "Unknown error"
            steps.append({"step": step_num, "title": "❌ Error", "content": f"Step: AI → Bot (GPT) | {err_msg}", "tokens": 0, "model": None, "cost_usd": None, "event_type": "error"})
            step_num += 1
        resp_step = {"step": step_num, "title": "Bot → User", "content": sent_reply or "(no response)", "tokens": 0, "model": None, "cost_usd": None, "event_type": "response_sent"}
        if action in ("human_handover", "human_handover_confirmed"):
            resp_step["event_type"] = "handover_triggered"
            resp_step["metadata"] = {"handover": True}
        steps.append(resp_step)
        total_cost = selector_cost + main_cost
        summary_parts = [f"Selector ({SELECTOR_MODEL}): {sel_pt + sel_ct} tokens, ${selector_cost:.6f}", f"Main GPT ({main_model}): {(pt or 0) + (ct or 0)} tokens, ${main_cost:.6f}", f"Total cost: ${total_cost:.6f}"]
        steps.append({"step": step_num + 1, "title": "📊 Summary (usage & cost)", "content": " | ".join(summary_parts), "tokens": (sel_pt + sel_ct) + (pt or 0) + (ct or 0), "model": None, "cost_usd": round(total_cost, 6)})
        flow_steps, msg_type = _prepend_multimodal_steps(steps, 1)
    else:
        tool_round_trips = flow_meta.get("tool_round_trips") or []
        ai_first = flow_meta.get("ai_first_response")
        ai_error = flow_meta.get("error")
        ai_raw_or_error = flow_meta.get("ai_raw_response") or (f"AI error: {ai_error}" if ai_error else None)
        pt = flow_meta.get("prompt_tokens")
        ct = flow_meta.get("completion_tokens")
        main_model = flow_meta.get("model") or "gpt-5.1"
        main_cost = flow_meta.get("cost_usd") or 0.0
        steps = [
            {"step": 1, "title": "User → Bot", "content": user_input_to_process, "tokens": 0, "model": None, "cost_usd": None},
        ]
        cust_ctx = flow_meta.get("customer_context_sent")
        if cust_ctx:
            steps.append({"step": 2, "title": "Bot → AI (Customer context)", "content": cust_ctx, "tokens": 0, "model": None, "cost_usd": None, "event_type": "customer_context_sent"})
        steps.append({"step": len(steps) + 1, "title": "Bot → AI", "content": flow_meta.get("bot_sent_to_ai") or flow_meta.get("ai_query_summary") or "Query + context sent to GPT.", "tokens": pt, "model": main_model, "cost_usd": round(flow_meta.get("input_cost_usd") or 0, 6) if (flow_meta.get("input_cost_usd") is not None) else None, "event_type": "main_ai_started"})
        step_num = len(steps) + 1
        if tool_round_trips:
            steps.append({"step": step_num, "title": "AI → Bot (requested tools)", "content": ai_first or "AI requested tool calls.", "tokens": 0, "model": None, "cost_usd": None})
            step_num += 1
            for i, tr in enumerate(tool_round_trips):
                steps.append({
                    "step": step_num,
                    "title": f"AI requested: {tr.get('ai_requested', '?')}",
                    "content": f"Args: {tr.get('args', '{}')}",
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                })
                step_num += 1
                exec_step = {
                    "step": step_num,
                    "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})",
                    "content": tr.get("bot_returned", ""),
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
                if tr.get("backend_execution"):
                    exec_step["metadata"] = {"backend_execution": tr["backend_execution"]}
                steps.append(exec_step)
                step_num += 1
            steps.append({"step": step_num, "title": "AI → Bot (final response)", "content": ai_raw_or_error or "(no content)", "tokens": ct, "model": main_model, "cost_usd": round(flow_meta.get("output_cost_usd") or 0, 6) if (flow_meta.get("output_cost_usd") is not None) else None, "event_type": "main_ai_completed"})
            step_num += 1
        else:
            steps.append({"step": step_num, "title": "AI → Bot", "content": ai_raw_or_error or f"GPT returned. Model: {main_model} | Tokens: {(pt or 0) + (ct or 0)} | Time: {response_time_ms:.0f}ms", "tokens": ct, "model": main_model, "cost_usd": round(main_cost, 6) if main_cost else None, "event_type": "main_ai_completed"})
            step_num += 1
        if flow_meta.get("error") or _flow_error_reason:
            err_msg = flow_meta.get("error") or _flow_error_reason or "Unknown error"
            steps.append({"step": step_num, "title": "❌ Error", "content": f"Step: AI → Bot | {err_msg}", "tokens": 0, "model": None, "cost_usd": None, "event_type": "error"})
            step_num += 1
        resp_step = {"step": step_num, "title": "Bot → User", "content": sent_reply or "(no response)", "tokens": 0, "model": None, "cost_usd": None, "event_type": "response_sent"}
        if action in ("human_handover", "human_handover_confirmed"):
            resp_step["event_type"] = "handover_triggered"
            resp_step["metadata"] = {"handover": True}
        steps.append(resp_step)
        summary_parts = [f"GPT ({main_model}): {(pt or 0) + (ct or 0)} tokens, ${main_cost:.6f}", f"Total cost: ${main_cost:.6f}"]
        steps.append({"step": step_num + 1, "title": "📊 Summary (usage & cost)", "content": " | ".join(summary_parts), "tokens": (pt or 0) + (ct or 0), "model": None, "cost_usd": round(main_cost, 6)})
        flow_steps, msg_type = _prepend_multimodal_steps(steps, 1)
    flow_error_for_log = flow_meta.get("error") or _flow_error_reason
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
        customer_context_sent=flow_meta.get("customer_context_sent"),
        ai_raw_response=flow_meta.get("ai_raw_response"),
        model=flow_meta.get("model"),
        tokens=flow_meta.get("tokens"),
        prompt_tokens=flow_meta.get("prompt_tokens"),
        completion_tokens=flow_meta.get("completion_tokens"),
        cost_usd=flow_meta.get("cost_usd"),
        input_cost_usd=flow_meta.get("input_cost_usd"),
        output_cost_usd=flow_meta.get("output_cost_usd"),
        response_time_ms=response_time_ms,
        tool_calls=flow_meta.get("tool_calls"),
        flow_steps=flow_steps,
        flow_error=flow_error_for_log,
        token_source="backend" if flow_meta.get("prompt_tokens") is not None else None,
        message_type=msg_type,
    )

    # Token counting and cost: prefer real GPT usage from flow_meta when available
    prompt_tokens = flow_meta.get("prompt_tokens") or 0
    completion_tokens = flow_meta.get("completion_tokens") or 0
    cost = flow_meta.get("cost_usd") or 0.0
    if cost == 0 and user_input_to_process.strip() and not user_input_to_process.lower().startswith('/start'):
        prompt_tokens = count_tokens(get_system_instruction(user_id, current_preferred_lang) + "\n\n" + user_input_to_process)
        completion_tokens = count_tokens(bot_reply_text)
        total_tokens = prompt_tokens + completion_tokens
        cost = (prompt_tokens / 1_000_000 * 1.25) + (completion_tokens / 1_000_000 * 10)  # gpt-5.1 pricing
        print(f"[_process_and_respond] 🔹 Prompt tokens: {prompt_tokens} | Completion: {completion_tokens} | Est. cost: ${cost:.6f}")
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
        model=flow_meta.get("model") or "gpt-5.1",
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
