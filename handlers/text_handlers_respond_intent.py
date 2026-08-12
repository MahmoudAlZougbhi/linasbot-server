"""Intent and booking-claim helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from handlers.text_handlers_respond_keywords import (
    _GREETING_PREFIX_RE,
    _LEADING_ADDRESS_RE,
    AFFIRMATIVE_CONFIRMATION_PHRASES,
    AFFIRMATIVE_CONFIRMATION_TOKENS,
    ALLOWED_GENERAL_QUERIES,
    BODY_AREA_HINT_KEYWORDS,
    BOOKING_INTENT_CONFIRMATION_KEYWORDS,
    BOOKING_OFFER_QUESTION_RE,
    CLINIC_SCOPE_KEYWORDS,
    GENERAL_QUESTION_PREFIX_RE,
    GREETING_OPENERS,
    LASER_HAIR_INTENT_KEYWORDS,
    NEGATIVE_CONFIRMATION_PHRASES,
    NEGATIVE_CONFIRMATION_TOKENS,
    OFF_TOPIC_KEYWORDS,
    PRICE_INTENT_KEYWORDS,
)


def _parse_tool_round_bot_returned(bot_returned: str) -> Any:
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
    lang_key = (lang or "ar").lower()
    if lang_key == "en":
        return (
            "Your appointment is not saved in our system yet—the booking step did not complete successfully. "
            "Please do not consider it confirmed until the system confirms it; I will complete the booking next."
        )
    if lang_key == "fr":
        return (
            "Votre rendez-vous n'est pas encore enregistré dans notre système — la réservation n'a pas abouti. "
            "Merci de ne pas le considérer comme confirmé tant que le système ne l'a pas validé."
        )
    return (
        "لم يُسجَّل الموعد بعد في نظام العيادة لأن خطوة الحجز لم تُكمَل بنجاح. "
        "من فضلك لا تعتبري الموعد مؤكداً قبل ما يظهر تأكيد من النظام—رح كمّل إجراء الحجز بالأدوات المناسبة."
    )

def _reply_claims_booking_done(text: str) -> bool:
    """
    True when the assistant wording tells the user the booking already happened
    or that the booking request was already sent/submitted to the system.
    A summary + yes/no confirmation request must remain allowed.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    positive_done_patterns = [
        r"تم(?:\s+)?(?:تأكيد|تثبيت|حجز)\s+الموعد",
        r"تم(?:\s+)?تأكيد\s+حجز(?:ك|كم)?",
        r"تم(?:\s+)?تثبيت\s+حجز(?:ك|كم)?",
        r"حجز(?:ك|كم)?\s+تم(?:\s+)?تأكيده?",
        r"صار(?:\s+)?(?:الحجز|الموعد)\s+(?:مؤكد|مثبت)",
        r"الموعد(?:\s+)?(?:صار|أصبح)?\s*(?:مؤكد|مثبت|محجوز)",
        r"بعث(?:ت|نا)\s+الطلب(?:\s+)?(?:للحجز)?",
        r"تم(?:\s+)?إرسال\s+الطلب(?:\s+)?(?:للحجز)?",
        r"تم(?:\s+)?رفع\s+الطلب(?:\s+)?(?:للحجز)?",
        r"submitted\s+the\s+booking",
        r"sent\s+the\s+booking\s+request",
        r"booking\s+request\s+has\s+been\s+sent",
        r"your appointment is confirmed",
        r"appointment is confirmed",
        r"appointment has been booked",
        r"booked successfully",
        r"rendez-vous.*confirm",
    ]
    request_confirmation_patterns = [
        r"هل .*مظبوط",
        r"هل .*صحيح",
        r"فيك[ي]?\s+تأك",
        r"confirm",
        r"yes/no",
        r"before i .*complete",
        r"قبل .*أكم",
    ]
    if any(re.search(p, t, flags=re.IGNORECASE) for p in request_confirmation_patterns):
        return False
    return any(re.search(p, t, flags=re.IGNORECASE) for p in positive_done_patterns)

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
        "se3a",
        "ساعة",
        "saat",
        "hour",
        "book",
        "حجز",
        "appointment",
        "موعد",
        "hotle",
        "hotel",
        "فندق",
        "coffee",
        "قهوة",
        "table",
        "room",
        "laser",
        "ليزر",
        "tattoo",
        "price",
        "سعر",
        "دكتور",
        "dr.",
        "clinic",
        "عيادة",
        "today",
        "tomorrow",
        "غدا",
        "بكرا",
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

