"""Deterministic WhatsApp routing for appointment and human-agent requests on social DMs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from services.conversation_router import get_gender_from_message, is_human_request


SOCIAL_CHANNELS = {"instagram", "facebook"}

# Public business WhatsApp contacts (authoritative defaults). Env vars override per key.
DEFAULT_SOCIAL_WHATSAPP_CONTACTS = {
    "SOCIAL_WHATSAPP_BEIRUT_FEMALE": "+96178847527",
    "SOCIAL_WHATSAPP_ANTELIAS_FEMALE": "+96170707354",
    "SOCIAL_WHATSAPP_BEIRUT_MALE": "+96171534928",
    "SOCIAL_WHATSAPP_ANTELIAS_MALE": "+96171226082",
    "SOCIAL_WHATSAPP_TATTOO_REMOVAL": "+96171534928",
}

_APPOINTMENT_RE = re.compile(
    r"(?:"
    r"حجز|احجز|أحجز|موعد|مواعيد|تأجيل|اجل|أجل|غيّر\s*موعد|غير\s*موعد|إلغاء\s*موعد|الغاء\s*موعد|"
    r"book(?:ing)?|appointment|reserve|reservation|reschedul|cancel\s+(?:my\s+)?appointment|"
    r"rendez[- ]?vous|\brdv\b|réserv|reporter\s+(?:mon\s+)?rendez|"
    r"7ajz|hajz|mou3?ed|maw3?ed|bade\s*e?7?jez|baddi\s*e?7?jez|bade\s*7jez|baddi\s*7jez"
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


@dataclass(frozen=True)
class SocialContactRouteResult:
    reply: str
    intent: str
    branch: Optional[str] = None
    gender: Optional[str] = None
    contact_env: Optional[str] = None
    tattoo_removal: bool = False


def is_social_channel(channel: Optional[str]) -> bool:
    return str(channel or "").strip().lower() in SOCIAL_CHANNELS


def is_appointment_request(message: str) -> bool:
    return bool(_APPOINTMENT_RE.search(message or ""))


def detect_branch(message: str) -> Optional[str]:
    text = message or ""
    # Prefer the more specific Antelias match when both appear.
    antelias = bool(_ANTELIAS_RE.search(text))
    beirut = bool(_BEIRUT_RE.search(text))
    if antelias and not beirut:
        return "antelias"
    if beirut and not antelias:
        return "beirut"
    if antelias and beirut:
        # Explicit Antelias usually wins when both are present ("not Beirut, Antelias").
        return "antelias"
    return None


def is_tattoo_removal_request(message: str) -> bool:
    return bool(_TATTOO_RE.search(message or ""))


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def wa_me_url(phone: str) -> str:
    return f"https://wa.me/{phone_digits(phone)}"


def resolve_social_whatsapp_number(env_name: str) -> Optional[str]:
    """Env override wins; otherwise use the tracked public default for that exact key."""
    override = (os.getenv(env_name) or "").strip()
    if override:
        return override
    default = DEFAULT_SOCIAL_WHATSAPP_CONTACTS.get(env_name)
    return default.strip() if default else None


def _language(language: Optional[str]) -> str:
    value = str(language or "ar").strip().lower()
    return value if value in {"ar", "en", "fr", "franco"} else "ar"


def _word_count(message: str) -> int:
    return len([part for part in re.split(r"\s+", (message or "").strip()) if part])


def _ask_branch(language: str) -> str:
    if language == "en":
        return "Of course. Which branch do you prefer: Beirut (Ramlet El Bayda) or Antelias?"
    if language == "fr":
        return "Bien sûr. Quelle agence préférez-vous : Beyrouth (Ramlet El Bayda) ou Antélias ?"
    return "أكيد. أي فرع بدك: بيروت (الرملة البيضاء) أو أنطلياس؟"


def _ask_gender(language: str) -> str:
    if language == "en":
        return "To give you the correct WhatsApp number, are you male or female?"
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


def _tattoo_contact_reply(language: str, phone: str) -> str:
    """Tattoo removal is Beirut-only and gender-independent."""
    whatsapp_url = wa_me_url(phone)
    if language == "en":
        return (
            "Tattoo removal is handled from our Beirut (Ramlet El Bayda) WhatsApp only—no calls "
            "(same contact for all genders; not Antelias):\n"
            f"{phone}\n{whatsapp_url}\n"
            "Appointments are completed by the team on WhatsApp, not inside Instagram or Facebook."
        )
    if language == "fr":
        return (
            "Le détatouage est géré uniquement via WhatsApp à Beyrouth (Ramlet El Bayda) — pas d'appels "
            "(même numéro pour tous les genres ; pas Antélias) :\n"
            f"{phone}\n{whatsapp_url}\n"
            "La réservation est finalisée avec l'équipe sur WhatsApp, pas sur Instagram ou Facebook."
        )
    return (
        "إزالة التاتو بتتم عبر واتساب فرع بيروت (الرملة البيضاء) فقط، من دون اتصالات "
        "(نفس الرقم لكل الأجناس، مش أنطلياس):\n"
        f"{phone}\n{whatsapp_url}\n"
        "الحجز بيتم مع الفريق على واتساب، مش من داخل إنستغرام أو فيسبوك."
    )


def _should_continue_active_flow(message: str) -> bool:
    """Keep collecting branch/gender for short answers; let side questions reach the AI."""
    if detect_branch(message) or get_gender_from_message(message):
        return True
    if is_appointment_request(message) or is_human_request(message) or is_tattoo_removal_request(message):
        return True
    return _word_count(message) <= 4


def route_social_contact_request(
    message: str,
    user_data: dict,
    known_gender: Optional[str],
    language: Optional[str] = None,
    force_intent: Optional[str] = None,
) -> Optional[SocialContactRouteResult]:
    """Return a deterministic reply when social DMs must be routed to WhatsApp."""
    state = user_data.setdefault("social_contact_flow", {})
    active_intent = state.get("intent")

    detected_intent = None
    if force_intent in {"booking", "human"}:
        detected_intent = force_intent
    elif is_human_request(message):
        detected_intent = "human"
    elif is_appointment_request(message):
        detected_intent = "booking"
    elif active_intent in {"booking", "human"} and _should_continue_active_flow(message):
        detected_intent = active_intent

    if not detected_intent:
        if not state:
            user_data.pop("social_contact_flow", None)
        return None

    state["intent"] = detected_intent
    detected_branch = detect_branch(message)
    if detected_branch:
        state["branch"] = detected_branch

    tattoo = bool(state.get("tattoo_removal")) or is_tattoo_removal_request(message)
    state["tattoo_removal"] = tattoo

    detected_gender = get_gender_from_message(message)
    gender = detected_gender or (known_gender if known_gender in {"male", "female"} else None)
    if detected_gender:
        state["gender"] = detected_gender
    elif state.get("gender") in {"male", "female"}:
        gender = state["gender"]

    lang = _language(language)

    # Tattoo removal: Beirut-only, all genders, never ask Antelias/gender for contact selection.
    if tattoo:
        phone = resolve_social_whatsapp_number("SOCIAL_WHATSAPP_TATTOO_REMOVAL")
        if not phone:
            return SocialContactRouteResult(
                _missing_contact(lang),
                detected_intent,
                branch="beirut",
                gender=gender,
                contact_env="SOCIAL_WHATSAPP_TATTOO_REMOVAL",
                tattoo_removal=True,
            )
        reply = _tattoo_contact_reply(lang, phone)
        user_data.pop("social_contact_flow", None)
        return SocialContactRouteResult(
            reply,
            detected_intent,
            branch="beirut",
            gender=gender,
            contact_env="SOCIAL_WHATSAPP_TATTOO_REMOVAL",
            tattoo_removal=True,
        )

    branch = state.get("branch")
    if not branch:
        return SocialContactRouteResult(_ask_branch(lang), detected_intent, gender=gender)
    if not gender:
        return SocialContactRouteResult(_ask_gender(lang), detected_intent, branch=branch)

    env_name = f"SOCIAL_WHATSAPP_{branch.upper()}_{gender.upper()}"
    phone = resolve_social_whatsapp_number(env_name)
    if not phone:
        return SocialContactRouteResult(
            _missing_contact(lang),
            detected_intent,
            branch=branch,
            gender=gender,
            contact_env=env_name,
        )

    reply = _laser_contact_reply(lang, branch, phone)
    user_data.pop("social_contact_flow", None)
    return SocialContactRouteResult(
        reply,
        detected_intent,
        branch=branch,
        gender=gender,
        contact_env=env_name,
    )
