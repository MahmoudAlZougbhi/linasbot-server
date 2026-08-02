"""Deterministic WhatsApp routing for appointment and human-agent requests on social DMs.

Normal Instagram/Facebook messages must reach the canonical Linas AI. This module only
intercepts after an explicit booking/human-agent (or tattoo-removal contact) intent, then
collects missing branch/gender one field at a time before returning a WhatsApp handoff.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from services.conversation_router import get_gender_from_message, is_human_request

SOCIAL_CHANNELS = {"instagram", "facebook"}

# Pending handoff collection TTL (seconds). After expiry, the next message returns to AI.
SOCIAL_CONTACT_FLOW_TTL_SECONDS = 30 * 60

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


@dataclass(frozen=True)
class SocialContactRouteResult:
    reply: str
    intent: str
    branch: str | None = None
    gender: str | None = None
    contact_env: str | None = None
    tattoo_removal: bool = False


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


def resolve_social_whatsapp_number(env_name: str) -> str | None:
    """Env override wins; otherwise use the tracked public default for that exact key."""
    override = (os.getenv(env_name) or "").strip()
    if override:
        return override
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


def _is_greeting_only(message: str) -> bool:
    return bool(_GREETING_ONLY_RE.match((message or "").strip()))


def _is_cancel_handoff(message: str) -> bool:
    return bool(_CANCEL_HANDOFF_RE.search(message or ""))


def _explicit_handoff_intent(message: str) -> str | None:
    if is_human_request(message):
        return "human"
    if is_appointment_request(message) or is_tattoo_removal_request(message):
        return "booking"
    return None


def _flow_state_key(user_data: dict) -> str:
    """Isolate pending handoff state by channel (+ meta account when present)."""
    channel = str(user_data.get("channel") or "").strip().lower() or "unknown"
    account = str(user_data.get("meta_account_id") or "").strip()
    if account:
        return f"social_contact_flow::{channel}::{account}"
    return f"social_contact_flow::{channel}"


def _get_flow_state(user_data: dict) -> dict:
    key = _flow_state_key(user_data)
    # Migrate legacy un-namespaced state once, only for the same channel.
    legacy = user_data.get("social_contact_flow")
    if isinstance(legacy, dict) and legacy.get("intent") and key not in user_data:
        legacy_channel = str(legacy.get("channel") or "").strip().lower()
        current = str(user_data.get("channel") or "").strip().lower()
        if not legacy_channel or legacy_channel == current:
            user_data[key] = dict(legacy)
        user_data.pop("social_contact_flow", None)
    state = user_data.get(key)
    return state if isinstance(state, dict) else {}


def _set_flow_state(user_data: dict, state: dict) -> None:
    key = _flow_state_key(user_data)
    state = dict(state)
    state["channel"] = str(user_data.get("channel") or "").strip().lower()
    state["meta_account_id"] = str(user_data.get("meta_account_id") or "").strip()
    state["updated_at"] = time.time()
    if "started_at" not in state:
        state["started_at"] = state["updated_at"]
    user_data[key] = state
    # Never keep a cross-channel legacy blob around.
    user_data.pop("social_contact_flow", None)


def _clear_flow_state(user_data: dict) -> None:
    user_data.pop(_flow_state_key(user_data), None)
    user_data.pop("social_contact_flow", None)


def _state_expired(state: dict) -> bool:
    """Expire after SOCIAL_CONTACT_FLOW_TTL_SECONDS of inactivity (updated_at)."""
    if not state:
        return False
    stamp = state.get("updated_at") or state.get("started_at")
    try:
        stamp_f = float(stamp or 0)
    except (TypeError, ValueError):
        return True
    return (time.time() - stamp_f) > SOCIAL_CONTACT_FLOW_TTL_SECONDS


def _is_valid_continuation(message: str, state: dict) -> bool:
    """Only branch/gender answers (or re-stated handoff intent) continue a pending flow."""
    if detect_branch(message):
        return True
    if get_gender_from_message(message):
        return True
    if _explicit_handoff_intent(message):
        return True
    return False


def _is_topic_change_during_handoff(message: str, state: dict) -> bool:
    """Greetings, cancels, or non-answer text while waiting for branch/gender → return to AI."""
    if not state.get("intent"):
        return False
    if _is_cancel_handoff(message) or _is_greeting_only(message):
        return True
    # Waiting for a field but message is neither a valid answer nor a new handoff intent.
    return not _is_valid_continuation(message, state)


def route_social_contact_request(
    message: str,
    user_data: dict,
    known_gender: str | None,
    language: str | None = None,
    force_intent: str | None = None,
) -> SocialContactRouteResult | None:
    """Return a deterministic WhatsApp-handoff reply only for explicit social handoff flows.

    ``force_intent`` (from GPT/router) cannot start a new handoff by itself. A new flow
    starts only when the user message explicitly requests booking/human/tattoo contact.
    Pending branch/gender collection continues only on valid answers; greetings, cancels,
    topic changes, and expired state return None so the canonical AI handles the message.
    """
    state = _get_flow_state(user_data)
    if state and _state_expired(state):
        _clear_flow_state(user_data)
        state = {}

    explicit = _explicit_handoff_intent(message)
    active_intent = state.get("intent") if state.get("intent") in {"booking", "human"} else None

    # GPT/router hints may continue an already-open flow, but never open a new one alone.
    forced = force_intent if force_intent in {"booking", "human"} else None

    detected_intent = None
    if explicit:
        detected_intent = explicit
    elif active_intent and _is_valid_continuation(message, state):
        detected_intent = active_intent
    elif forced and active_intent == forced and _is_valid_continuation(message, state):
        detected_intent = forced
    elif forced and explicit:
        detected_intent = forced

    if active_intent and not detected_intent:
        if _is_topic_change_during_handoff(message, state):
            _clear_flow_state(user_data)
        return None

    if not detected_intent:
        if not state:
            _clear_flow_state(user_data)
        return None

    if _is_cancel_handoff(message) and not explicit:
        _clear_flow_state(user_data)
        return None

    state = dict(state) if state else {}
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
    _set_flow_state(user_data, state)

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
        _clear_flow_state(user_data)
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
    _clear_flow_state(user_data)
    return SocialContactRouteResult(
        reply,
        detected_intent,
        branch=branch,
        gender=gender,
        contact_env=env_name,
    )


def expire_social_contact_flows_in_user_data(user_data: dict) -> int:
    """Clear expired/invalid social handoff blobs on a user_data dict. Returns cleared count."""
    cleared = 0
    for key in list(user_data.keys()):
        if key != "social_contact_flow" and not str(key).startswith("social_contact_flow::"):
            continue
        state = user_data.get(key)
        if not isinstance(state, dict) or not state.get("intent") or _state_expired(state):
            user_data.pop(key, None)
            cleared += 1
    return cleared


def reset_social_contact_flow_for_sender(user_data: dict) -> bool:
    """Reset pending handoff for the current channel/account scope only."""
    before = _get_flow_state(user_data)
    _clear_flow_state(user_data)
    return bool(before)
