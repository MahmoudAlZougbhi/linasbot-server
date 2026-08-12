"""Intent/reply keyword constants for text respond path."""

from __future__ import annotations

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
    "اه",
    "اي",
    "ايه",
    "نعم",
    "تمام",
    "اكيد",
    "أكيد",
    "yes",
    "yeah",
    "yep",
    "oui",
    "ok",
    "okay",
    "sure",
    "eh",
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
