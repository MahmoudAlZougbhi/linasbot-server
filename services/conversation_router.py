# -*- coding: utf-8 -*-
"""
Conversation Router – AI Smart Employee Architecture

Code-level router that returns one of 6 actions BEFORE GPT:
greeting, ask_gender, ask_clarification, answer_question, human_handover, fallback

Priority order (Plan §4):
1. Human request → human_handover
2. human_handover_active → None (handled elsewhere)
3. awaiting_gender + user answered gender → answer_question (resume_original_question)
4. awaiting_clarification + user provided detail → answer_question (resume_original_question)
5. Greeting only (no pending state) → greeting
6. Gender required + unknown → ask_gender
7. Enough info → answer_question
8. Missing info → ask_clarification
9. Otherwise → fallback
"""

import re
from typing import Optional

import config

# --- Human handover intent (meaning-based; common phrases) ---
HUMAN_REQUEST_PATTERNS = [
    # Arabic
    r"بدي\s*(?:أحكي|أتكلم|أتكلم)\s*(?:مع|ل)",
    r"حد\s*(?:يحكي|يتكلم)\s*معي",
    r"موظف",
    r"موظفة",
    r"إنسان",
    r"شخص\s*حقيقي",
    r"واحد\s*(?:منكم|منكن)",
    r"بدي\s*إيا",
    r"بدي\s*حد",
    r"حابب\s*أحكي\s*مع",
    r"ممكن\s*(?:حد|واحد)\s*(?:يحكي|يتكلم)",
    r"أريد\s*التحدث\s*مع",
    r"أريد\s*موظف",
    r"أريد\s*إنسان",
    # English
    r"speak\s*(?:to|with)\s*(?:a\s*)?(?:human|person|agent|representative|employee)",
    r"talk\s*(?:to|with)\s*(?:a\s*)?(?:human|person|agent|representative)",
    r"want\s*(?:a\s*)?(?:human|person|agent|representative|employee)",
    r"need\s*(?:a\s*)?(?:human|person|agent|representative)",
    r"connect\s*me\s*(?:to|with)",
    r"transfer\s*me\s*(?:to|with)",
    r"real\s*person",
    r"human\s*agent",
    # French
    r"parler\s*(?:à|avec)\s*(?:un\s*)?(?:humain|employé|agent|personne)",
    r"vraie\s*personne",
    r"agent\s*humain",
]
HUMAN_REQUEST_RE = re.compile("|".join(f"({p})" for p in HUMAN_REQUEST_PATTERNS), re.IGNORECASE | re.UNICODE)

# Simple keywords (fallback when regex misses)
HUMAN_REQUEST_KEYWORDS = [
    "human", "موظف", "موظفة", "حد يحكي", "بدي حد", "واحد منكم", "شخص حقيقي",
    "agent", "representative", "employee", "person", "parler à un", "vraie personne",
]

# --- Gender answer patterns ---
GENDER_MALE_PATTERNS = [
    r"^(?:ذكر|male|homme|شب|شاب|رجل|رجال|أنا\s*شب|أنا\s*شاب|i'm\s*male|je\s*suis\s*homme)",
    r"\b(?:ذكر|male|homme|شب|شاب)\b",
]
GENDER_FEMALE_PATTERNS = [
    r"^(?:أنثى|female|femme|صبية|بنت|امرأة|نساء|أنا\s*صبية|أنا\s*بنت|i'm\s*female|je\s*suis\s*femme)",
    r"\b(?:أنثى|female|femme|صبية|بنت)\b",
]

# --- Greeting-only patterns (no service/pricing/booking) ---
GREETING_ONLY_PATTERNS = [
    r"^(?:مرحبا|مرحبا|marhaba|هلا|أهلا|سلام|السلام\s*عليكم)",
    r"^(?:hello|hi|hey|good\s*morning|good\s*evening)",
    r"^(?:bonjour|salut|coucou)",
]
GREETING_RE = re.compile("|".join(f"({p})" for p in GREETING_ONLY_PATTERNS), re.IGNORECASE | re.UNICODE)

# Messages that are ONLY greeting (short, no other content)
SERVICE_PRICING_BOOKING_KEYWORDS = [
    "سعر", "اسعار", "كم", "قديش", "أديش", "price", "cost", "pricing", "combien", "prix",
    "ليزر", "شعر", "وشم", "تاتو", "laser", "hair", "tattoo", "حجز", "booking", "reservation",
    "خدمة", "service", "علاج", "treatment", "جلسة", "session",
]

# --- Vague messages that need clarification ---
VAGUE_CLARIFICATION_PATTERNS = [
    r"^شو\s*الأسعار\s*[؟?]?$",
    r"^كم\s*السعر\s*[؟?]?$",
    r"^بدي\s*أعرف\s*[؟?]?$",
    r"^بدي\s*استفسر\s*[؟?]?$",
    r"^بدي\s*أحجز\s*[؟?]?$",
    r"^prices?\s*[?]?$",
    r"^how\s*much\s*[?]?$",
]
VAGUE_RE = re.compile("|".join(f"({p})" for p in VAGUE_CLARIFICATION_PATTERNS), re.IGNORECASE | re.UNICODE)

# --- Service-related (needs gender when unknown) ---
SERVICE_INTENT_KEYWORDS = [
    "ليزر", "شعر", "وشم", "تاتو", "laser", "hair", "tattoo", "جلسة", "session",
    "علاج", "treatment", "خدمة", "service", "سعر", "اسعار", "price", "pricing",
    "إزالة", "removal", "تبييض", "whitening", "حب شباب", "acne",
]


def _normalize(text: str) -> str:
    return (text or "").strip()


def is_human_request(message: str) -> bool:
    """Detect if user wants to speak with a human/agent/employee."""
    t = _normalize(message)
    if len(t) < 3:
        return False
    if HUMAN_REQUEST_RE.search(t):
        return True
    t_lower = t.lower()
    return any(kw in t_lower for kw in HUMAN_REQUEST_KEYWORDS)


def is_gender_answer(message: str) -> bool:
    """Detect if message is a gender answer (male/female)."""
    return get_gender_from_message(message) is not None


def get_gender_from_message(message: str) -> Optional[str]:
    """Extract gender from message. Returns 'male', 'female', or None."""
    t = _normalize(message)
    if len(t) > 30:  # Too long to be just gender
        return None
    for p in GENDER_MALE_PATTERNS:
        if re.search(p, t, re.IGNORECASE | re.UNICODE):
            return "male"
    for p in GENDER_FEMALE_PATTERNS:
        if re.search(p, t, re.IGNORECASE | re.UNICODE):
            return "female"
    short = t.lower().replace(" ", "")
    if short in ("male", "ذكر", "شب", "شاب", "homme"):
        return "male"
    if short in ("female", "أنثى", "صبية", "بنت", "femme"):
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
    return any(kw in t for kw in SERVICE_INTENT_KEYWORDS)


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


def route(user_id: str, message: str, state: dict) -> Optional[str]:
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
    has_pending = any([
        state.get("awaiting_gender"),
        state.get("awaiting_clarification"),
        state.get("awaiting_name"),
    ])
    if not has_pending and is_greeting_only(msg):
        return "greeting"

    # 6. Gender required + unknown
    if needs_gender_for_service(msg) and state.get("gender") == "unknown":
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
    "ar": "مرحباً! 😊 أنا Marwa المساعدة الذكية من Lina's Laser Center 🌷 كيف فيني أساعدك اليوم؟",
    "en": "Hello! 😊 I'm Marwa, the smart assistant from Lina's Laser Center 🌷 How can I help you today?",
    "fr": "Bonjour ! 😊 Je suis Marwa, l'assistante intelligente de Lina's Laser Center 🌷 Comment puis-je vous aider aujourd'hui ?",
    "franco": "Marhaba! 😊 Ana Marwa el mosa3de el zekiyye men Lina's Laser Center 🌷 kif fini se3dik el yom?",
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
