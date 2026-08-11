"""Social contact routing detection, constants, and reply helpers (LOC split)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from services.conversation_router import get_gender_from_message, is_human_request

SOCIAL_CHANNELS = {"instagram", "facebook"}

# Pending handoff collection TTL (seconds). After expiry, the next message returns to AI.
SOCIAL_CONTACT_FLOW_TTL_SECONDS = 30 * 60

# Durable, customer-selected social booking preference.  This is intentionally
# separate from the legacy/global ``gender`` profile field: a social preference
# is scoped to one workspace + channel + business asset + sender and is not a
# claim about a customer's biological identity.
SOCIAL_BOOKING_PREFERENCES_FIELD = "social_booking_preferences"
SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX = "social_booking_preference::v1::"

# Public business WhatsApp contacts for supported laser booking handoff (env overrides per key).
# Tattoo removal is intentionally absent — unsupported services never receive a WhatsApp route.
DEFAULT_SOCIAL_WHATSAPP_CONTACTS = {
    "SOCIAL_WHATSAPP_BEIRUT_FEMALE": "+96178847527",
    "SOCIAL_WHATSAPP_ANTELIAS_FEMALE": "+96170707354",
    "SOCIAL_WHATSAPP_BEIRUT_MALE": "+96171534928",
    "SOCIAL_WHATSAPP_ANTELIAS_MALE": "+96171226082",
}

_APPOINTMENT_RE = re.compile(
    r"(?:"
    # Explicit booking verbs / appointment actions (not bare "hours/schedule" words)
    r"حجز|احجز|أحجز|أريد\s*موعد|بدي\s*موعد|بدّي\s*موعد|تأجيل|اجل|أجل|غيّر\s*موعد|غير\s*موعد|إلغاء\s*موعد|الغاء\s*موعد|"
    r"(?<![A-Za-z])موعد(?!\s*العمل)(?!\s*الدوام)(?!\s*الفتح)|"
    r"book(?:ing)?|appointment|reserve|reservation|reschedul|cancel\s+(?:my\s+)?appointment|"
    r"rendez[- ]?vous|\brdv\b|réserv|reporter\s+(?:mon\s+)?rendez|"
    r"7ajz|hajz|"
    r"bade\s*(?:a|e)?7?jez|baddi\s*(?:a|e)?7?jez|bade\s*7jez|baddi\s*7jez|"
    r"bade\s*a7jez|baddi\s*a7jez|bade\s*ahjez|baddi\s*ahjez"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# Opening-hours / schedule questions must stay on AI (do not start handoff).
_HOURS_QUESTION_RE = re.compile(
    r"(?:"
    r"مواعيد\s*(?:العمل|الدوام|الفتح|الافتتاح)|ساعات\s*(?:العمل|الدوام)|دوامكن|دوامكم|"
    r"open(?:ing)?\s*hours|working\s*hours|what\s*time\s*do\s*you\s*open|"
    r"horaires?|heures?\s*d[' ]ouverture"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_TATTOO_RE = re.compile(
    r"(?:تاتو|وشم|tattoo|tatouage|détatouage|detatouage|tatou|izalet\s*al?\s*tatto|إزالة\s*التاتو|ازالة\s*التاتو)",
    re.IGNORECASE | re.UNICODE,
)
_ANTELIAS_RE = re.compile(
    r"(?:أنطلياس|انطلياس|أنتلياس|انتلياس|أنتيلياس|انتيلياس|"
    r"antelias|antelyas|antlias|antilyas|antélias)",
    re.IGNORECASE | re.UNICODE,
)
_BEIRUT_RE = re.compile(
    r"(?:بيروت|beirut|beyrouth|beyrout|beyroot|bayrut|bayroot|"
    r"الرملة\s*البيضا(?:ء)?|رملة\s*البيضا(?:ء)?|"
    r"ramlet?\s*(?:el\s*)?bayd[aeh]?|ramleh\s*(?:el\s*)?bayda|"
    r"rmle(?:h)?(?:\s*(?:el\s*)?bayda)?)",
    re.IGNORECASE | re.UNICODE,
)
_CANCEL_HANDOFF_RE = re.compile(
    r"(?:"
    r"\b(?:cancel|stop|never\s*mind|forget\s*it|no\s*thanks|quit)\b|"
    r"إلغاء|الغي|بطّل|بطل|وليكن|ما\s*بدي|"
    r"\b(?:cancel|annule|oublie|laisse\s*tomber)\b|"
    r"\b(?:cancel|stop|ma\s*bade|ma\s*baddi|batal|batel)\b"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_GREETING_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"hello|hi|hey|yo|bonjour|salut|bonsoir|coucou|"
    r"مرحبا|أهلا|اهلا|هلا|سلام|أهلين|اهلين|marhaba|mar7aba|ahla|"
    r"good\s*morning|good\s*evening|good\s*afternoon"
    r")[\s!?.]*$",
    re.IGNORECASE | re.UNICODE,
)
_PREFERENCE_CHANGE_RE = re.compile(
    r"(?:"
    r"\b(?:change|update|set|use)\s+(?:my\s+)?(?:preference|category)?\s*(?:to|as)?\s*"
    r"(?:men|women|male|female)\b|"
    r"\buse\s+(?:men|women|male|female)\s+(?:from\s+now|going\s+forward)\b|"
    r"\b(?:i\s*am|i'm|je\s+suis)\s+(?:men|women|male|female|man|woman|homme|femme)\b|"
    r"(?:غي[ّير]|غير|بدّل|بدل|استعمل|استخدم).*(?:تفضيل|رجال|نساء|شاب|صبية)|"
    r"(?:أنا|انا)\s*(?:شاب|زلمة|رجل|صبية|بنت|مرة|مرا)"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_OTHER_PERSON_MALE_RE = re.compile(
    r"\bfor\s+(?:my\s+)?(?:husband|boyfriend|son|brother|father|male\s+friend|man\s+friend)\b",
    re.IGNORECASE,
)
_OTHER_PERSON_FEMALE_RE = re.compile(
    r"\bfor\s+(?:my\s+)?(?:wife|girlfriend|daughter|sister|mother|female\s+friend|woman\s+friend)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SocialContactRouteResult:
    reply: str
    intent: str
    branch: str | None = None
    gender: str | None = None
    contact_env: str | None = None
    tattoo_removal: bool = False
    # Set only when the customer explicitly selected their own future default.
    # The caller persists it in the existing customer profile document.
    preference_to_persist: str | None = None


@dataclass(frozen=True)
class SocialContactScope:
    tenant_id: str
    channel: str
    business_asset_id: str
    sender_id: str


class SocialContactScopeError(RuntimeError):
    """Raised when a social handoff cannot be isolated to one business and sender."""


def is_social_channel(channel: str | None) -> bool:
    return str(channel or "").strip().lower() in SOCIAL_CHANNELS


def is_appointment_request(message: str) -> bool:
    text = message or ""
    if _HOURS_QUESTION_RE.search(text):
        return False
    # Bare "مواعيد" without booking verbs is treated as hours/info, not booking.
    stripped = text.strip()
    if re.fullmatch(r"مواعيد\s*[؟?]?", stripped):
        return False
    if "مواعيد" in stripped and not re.search(r"حجز|احجز|أحجز|book|appointment|موعد\b", stripped):
        # e.g. "شو مواعيد العمل؟" — hours, not booking
        if _HOURS_QUESTION_RE.search(stripped) or re.search(r"العمل|الدوام|الفتح|دوام", stripped):
            return False
    return bool(_APPOINTMENT_RE.search(text))


def detect_branch(message: str) -> str | None:
    text = message or ""
    antelias = bool(_ANTELIAS_RE.search(text))
    beirut = bool(_BEIRUT_RE.search(text))
    if antelias and not beirut:
        return "antelias"
    if beirut and not antelias:
        return "beirut"
    if antelias and beirut:
        return "antelias"
    return None


def is_tattoo_removal_request(message: str) -> bool:
    return bool(_TATTOO_RE.search(message or ""))


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def wa_me_url(phone: str) -> str:
    return f"https://wa.me/{phone_digits(phone)}"


def resolve_social_whatsapp_number(env_name: str, *, tenant_id: str = "linas") -> str | None:
    """Resolve public WhatsApp contact for a matrix key.

    Precedence:
    1. Explicit env override for that exact key (ops).
    2. When ``CM_RUNTIME_MODE=published``, the published CM handoff contact
       (``env_name.lower()``) — never silently fall back to code defaults.
    3. Tracked ``DEFAULT_SOCIAL_WHATSAPP_CONTACTS`` (legacy mode only).
    """
    tenant = (tenant_id or "linas").strip() or "linas"
    override = (os.getenv(env_name) or "").strip() if tenant == "linas" else ""
    if override:
        return override

    # CM AI CONTROL PLANE — published handoff contacts when this tenant uses CM runtime.
    from services.cm.constants import tenant_uses_cm_runtime

    if tenant_uses_cm_runtime(tenant):
        try:
            from services.cm.schemas import HandoffPolicy
            from services.cm.version_store import load_published_content

            _pointer, sections = load_published_content(tenant)
            policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
            contact_id = env_name.strip().lower()
            for contact in policy.contacts:
                if contact.id != contact_id:
                    continue
                dtype, value = contact.resolved_destination()
                if not value:
                    return None
                if dtype in {"whatsapp", "phone"}:
                    return value
                return None
        except Exception as exc:
            print(f"[social_contact_routing] published handoff resolve failed for {env_name}: {exc}")
            return None
        return None

    # Never leak Lina's deterministic contact matrix into a SaaS tenant that has
    # not published its own handoff policy.
    if tenant != "linas":
        return None
    default = DEFAULT_SOCIAL_WHATSAPP_CONTACTS.get(env_name)
    return default.strip() if default else None


def clear_social_contact_flow(user_data: dict) -> None:
    """Clear legacy and channel-scoped pending social handoff state."""
    user_data.pop("social_contact_flow", None)
    for key in list(user_data.keys()):
        if str(key).startswith("social_contact_flow::"):
            user_data.pop(key, None)


def _language(language: str | None) -> str:
    value = str(language or "ar").strip().lower()
    return value if value in {"ar", "en", "fr", "franco"} else "ar"


def _ask_branch(language: str) -> str:
    if language == "en":
        return "Of course. Which branch do you prefer: Beirut (Ramlet El Bayda) or Antelias?"
    if language == "fr":
        return "Bien sûr. Quelle agence préférez-vous : Beyrouth (Ramlet El Bayda) ou Antélias ?"
    return "أكيد. أي فرع بدك: بيروت (الرملة البيضاء) أو أنطلياس؟"


def _ask_gender(language: str) -> str:
    if language == "en":
        return "To give you the correct WhatsApp number: Men or Women?"
    if language == "fr":
        return "Pour vous donner le bon numéro WhatsApp, êtes-vous un homme ou une femme ?"
    return "تمام. كرمال أعطيك رقم الواتساب الصح، حضرتك شاب أو صبية؟"


def _missing_contact(language: str) -> str:
    if language == "en":
        return "The WhatsApp contact for this selection is being updated. Please send us another message shortly."
    if language == "fr":
        return "Le numéro WhatsApp correspondant est en cours de mise à jour. Merci de nous réécrire dans quelques instants."
    return "رقم الواتساب لهيدا الاختيار عم يتم تحديثه. لو سمحت ابعتلنا رسالة كمان شوي."


def _laser_contact_reply(language: str, branch: str, phone: str) -> str:
    branch_ar = "بيروت (الرملة البيضاء)" if branch == "beirut" else "أنطلياس"
    branch_en = "Beirut (Ramlet El Bayda)" if branch == "beirut" else "Antelias"
    whatsapp_url = wa_me_url(phone)
    if language == "en":
        return (
            f"For appointments or to speak with a human agent for the {branch_en} branch, "
            f"contact us on WhatsApp only—no calls:\n"
            f"{phone}\n{whatsapp_url}\n"
            "Appointments are completed by the team on WhatsApp, not inside Instagram or Facebook."
        )
    if language == "fr":
        return (
            f"Pour prendre rendez-vous ou parler à un conseiller à l'agence de {branch_en}, "
            f"contactez-nous uniquement sur WhatsApp — pas d'appels :\n"
            f"{phone}\n{whatsapp_url}\n"
            "La réservation est finalisée avec l'équipe sur WhatsApp, pas sur Instagram ou Facebook."
        )
    return (
        f"للحجز أو للتواصل مع موظف بفرع {branch_ar}، تواصل معنا على واتساب فقط، من دون اتصالات:\n"
        f"{phone}\n{whatsapp_url}\n"
        "الحجز بيتم مع الفريق على واتساب، مش من داخل إنستغرام أو فيسبوك."
    )


def _unsupported_service_refuse_reply(language: str) -> str:
    """Owner-confirmed truth: tattoo removal is not offered — never hand off WhatsApp for it."""
    if language == "en":
        return (
            "Tattoo removal isn't one of the services we currently offer. "
            "I'm happy to help with laser hair removal or anything else we do provide."
        )
    if language == "fr":
        return (
            "Le détatouage ne fait pas partie des services que nous proposons actuellement. "
            "Je peux vous aider pour l'épilation laser ou toute autre prestation disponible."
        )
    return (
        "إزالة التاتو مش من ضمن الخدمات يلي منقدمها حالياً. "
        "فيني ساعدك بإزالة الشعر بالليزر أو بأي خدمة تانية من خدماتنا."
    )


def _preference_updated_reply(language: str, preference: str) -> str:
    label = "Men" if preference == "male" else "Women"
    if language == "en":
        return f"Got it. I’ll use {label} as your default for future booking handoffs."
    if language == "fr":
        return f"C’est noté. J’utiliserai {label} comme préférence par défaut pour vos prochains transferts de réservation."
    return "تمام. رح اعتمد هالتفضيل لطلبات الحجز الجاية."


def _preference_persistence_failed_reply(language: str) -> str:
    if language == "en":
        return "I can use that selection for this conversation, but I couldn’t save it for future booking handoffs yet."
    if language == "fr":
        return "Je peux utiliser ce choix pour cette conversation, mais je n’ai pas encore pu l’enregistrer pour vos prochains transferts."
    return "فيني اعتمد هالاختيار بهالمحادثة، بس ما قدرنا نحفظه لطلبات الحجز الجاية بعد."


def social_booking_preference_reply(language: str, preference: str, *, persisted: bool) -> str:
    """Return a truthful acknowledgement after the profile write outcome is known."""
    if persisted:
        return _preference_updated_reply(language, preference)
    return _preference_persistence_failed_reply(language)


def _is_greeting_only(message: str) -> bool:
    return bool(_GREETING_ONLY_RE.match((message or "").strip()))


def _is_cancel_handoff(message: str) -> bool:
    return bool(_CANCEL_HANDOFF_RE.search(message or ""))


def _explicit_preference_change(message: str) -> bool:
    return bool(_PREFERENCE_CHANGE_RE.search(message or ""))


def _other_person_booking_gender(message: str) -> str | None:
    """Detect a current-request booking override without changing the customer's default."""
    text = message or ""
    if _OTHER_PERSON_MALE_RE.search(text):
        return "male"
    if _OTHER_PERSON_FEMALE_RE.search(text):
        return "female"
    return None


def _message_gender_selection(message: str) -> tuple[str | None, bool]:
    """Return (gender, is_another_person_override) for the current message only."""
    other_person_gender = _other_person_booking_gender(message)
    if other_person_gender:
        return other_person_gender, True
    return get_gender_from_message(message), False


def _explicit_handoff_intent(message: str) -> str | None:
    if is_human_request(message):
        return "human"
    if is_appointment_request(message) or is_tattoo_removal_request(message):
        return "booking"
    return None
