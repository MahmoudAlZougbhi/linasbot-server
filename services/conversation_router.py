"""
Conversation Router – AI Smart Employee Architecture

Code-level router that returns one of 6 actions BEFORE GPT.
Pattern catalogs: conversation_router_patterns (LOC split).
"""

from __future__ import annotations

import re

from services.conversation_router_patterns import (
    BOOKING_OR_PRICE_KEYWORDS,
    GENDER_FEMALE_PATTERNS,
    GENDER_MALE_PATTERNS,
    GREETING_RE,
    HUMAN_REQUEST_KEYWORDS,
    HUMAN_REQUEST_RE,
    SERVICE_INTENT_KEYWORDS,
    SERVICE_PRICING_BOOKING_KEYWORDS,
    TATTOO_KEYWORDS,
    VAGUE_RE,
)


def _normalize(text: str) -> str:
    return (text or "").strip()


def is_human_request(message: str) -> bool:
    """Detect if user wants to speak with a human/agent/employee."""
    t = _normalize(message)
    if len(t) < 3:
        return False
    # Personal-care / product questions containing "person" must not escalate.
    t_lower = t.lower()
    if re.search(r"\bpersonal\b", t_lower) and not re.search(
        r"\b(?:real\s+person|speak|talk|human\s+agent)\b", t_lower
    ):
        return False
    if HUMAN_REQUEST_RE.search(t):
        return True
    return any(kw in t_lower for kw in HUMAN_REQUEST_KEYWORDS)


def is_gender_answer(message: str) -> bool:
    """Detect if message is a gender answer (male/female)."""
    return get_gender_from_message(message) is not None


def get_gender_from_message(message: str) -> str | None:
    """Extract gender from message. Returns 'male', 'female', or None.
    Works for long messages too (e.g. one line with booking + «ana shab» + name)."""
    t = _normalize(message)
    for p in GENDER_MALE_PATTERNS:
        if re.search(p, t, re.IGNORECASE | re.UNICODE):
            return "male"
    for p in GENDER_FEMALE_PATTERNS:
        if re.search(p, t, re.IGNORECASE | re.UNICODE):
            return "female"
    short = t.lower().replace(" ", "")
    if short in (
        "male",
        "man",
        "men",
        "boy",
        "m",
        "ذكر",
        "شب",
        "شاب",
        "homme",
        "زلمة",
        "zalame",
        "zalameh",
        "zalmeh",
        "shab",
        "rajol",
        "zakar",
    ):
        return "male"
    if short in (
        "female",
        "woman",
        "women",
        "girl",
        "f",
        "أنثى",
        "صبية",
        "بنت",
        "femme",
        "مرة",
        "مرا",
        "mara",
        "mra",
        "bent",
        "binit",
        "sabeye",
        "sabya",
        "onsa",
    ):
        return "female"
    return None


def has_clarification_content(message: str) -> bool:
    """Detect if message has substantive content (service name, detail) - not just greeting."""
    t = _normalize(message)
    if len(t) < 2:
        return False
    # Has service-related keywords
    t_lower = t.lower()
    if any(kw in t_lower for kw in SERVICE_PRICING_BOOKING_KEYWORDS):
        return True
    # Has at least 2 words (likely a real answer)
    words = t.split()
    if len(words) >= 2:
        return True
    # Single word but looks like service (e.g. "ليزر", "شعر")
    if len(t) >= 3 and not GREETING_RE.match(t):
        return True
    return False


def is_greeting_only(message: str) -> bool:
    """Message is only a greeting, no service/pricing/booking request."""
    t = _normalize(message)
    if len(t) > 50:  # Long messages likely have more content
        return False
    if not GREETING_RE.match(t):
        return False
    t_lower = t.lower()
    # Must NOT contain service/pricing/booking
    return not any(kw in t_lower for kw in SERVICE_PRICING_BOOKING_KEYWORDS)


def needs_gender_for_service(message: str) -> bool:
    """Message is about service/pricing/treatment - gender may be needed."""
    t = _normalize(message).lower()
    if not any(kw in t for kw in SERVICE_INTENT_KEYWORDS):
        return False

    # Informational tattoo questions are usually gender-neutral; avoid blocking answer.
    is_tattoo_only = any(kw in t for kw in TATTOO_KEYWORDS)
    has_booking_or_price = any(kw in t for kw in BOOKING_OR_PRICE_KEYWORDS)
    if is_tattoo_only and not has_booking_or_price:
        return False

    return True


def needs_clarification(message: str) -> bool:
    """Message is too vague - needs clarification (which service, etc.)."""
    t = _normalize(message)
    if VAGUE_RE.match(t):
        return True
    # Very short without context
    if len(t) <= 15 and not any(kw in t.lower() for kw in SERVICE_PRICING_BOOKING_KEYWORDS):
        return True
    return False


def has_enough_info(message: str, state: dict) -> bool:
    """Default: if we reach this point and don't need clarification, we have enough."""
    return not needs_clarification(message)


def route(user_id: str, message: str, state: dict) -> str | None:
    """
    Route user message to one of 6 actions.

    Returns: "human_handover" | "answer_question" | "greeting" | "ask_gender" | "ask_clarification" | "fallback"
    or None when human_handover_active (handled elsewhere).
    """
    msg = _normalize(message)
    if not msg:
        return "fallback"

    # 1. Human request (top priority)
    if is_human_request(msg):
        return "human_handover"

    # 2. Human takeover active - handled in text_handlers_respond before router
    if state.get("human_handover_active"):
        return None

    # 3. Awaiting gender + user answered gender → resume original_question
    if state.get("awaiting_gender") and is_gender_answer(msg):
        return "answer_question"

    # 4. Awaiting clarification + user provided detail → resume original_question
    if state.get("awaiting_clarification") and has_clarification_content(msg):
        return "answer_question"

    # 5. Greeting only - ONLY when no active pending state
    has_pending = any(
        [
            state.get("awaiting_gender"),
            state.get("awaiting_clarification"),
            state.get("awaiting_name"),
        ]
    )
    if not has_pending and is_greeting_only(msg):
        return "greeting"

    # 6. Gender required + unknown (but not if gender is already stated in this message)
    if needs_gender_for_service(msg) and state.get("gender") == "unknown":
        if get_gender_from_message(msg) in ("male", "female"):
            return "answer_question"
        return "ask_gender"

    # 7. Enough info
    if has_enough_info(msg, state):
        return "answer_question"

    # 8. Missing info
    if needs_clarification(msg):
        return "ask_clarification"

    # 9. Fallback
    return "fallback"


# --- Greeting templates (Phase 7) ---
GREETING_TEMPLATES = {
    "ar": "مرحباً! 😊 أنا مروى المساعدة الذكية من مركز ليناز ليزر 🌷 كيف فيني أساعدك اليوم؟",
    "en": "Hello! 😊 I'm Marwa, the smart assistant from Lina's Laser Center 🌷 How can I help you today?",
    "fr": "Bonjour ! 😊 Je suis Marwa, l'assistante intelligente de Lina's Laser Center 🌷 Comment puis-je vous aider aujourd'hui ?",
    "franco": "مرحباً! 😊 أنا مروى المساعدة الذكية من مركز ليناز ليزر 🌷 كيف فيني أساعدك اليوم؟",
}

# --- Fallback templates (Phase 11) ---
FALLBACK_TEMPLATES = {
    "ar": "أكيد، فيك توضحلي أكتر شو الخدمة أو الموضوع اللي بدك تستفسر عنه؟",
    "en": "Sure, could you tell me more about which service or topic you'd like to know about?",
    "fr": "Bien sûr, pourriez-vous préciser quel service ou sujet vous intéresse ?",
    "franco": "أكيد، فيك توضحلي أكتر شو الخدمة أو الموضوع اللي بدك تستفسر عنه؟",
}

# --- Ask clarification templates (Phase 9) ---
ASK_CLARIFICATION_TEMPLATES = {
    "ar": "أكيد، لأي خدمة بدك الأسعار أو المعلومات؟ (ليزر شعر، إزالة وشم، تبييض، إلخ)",
    "en": "Sure! Which service would you like prices or information about? (hair removal, tattoo removal, whitening, etc.)",
    "fr": "Bien sûr ! Pour quel service souhaitez-vous des prix ou des informations ? (épilation, tatouage, blanchiment, etc.)",
    "franco": "أكيد، لأي خدمة بدك الأسعار أو المعلومات؟ (ليزر شعر، إزالة وشم، تبييض، إلخ)",
}
