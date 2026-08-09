"""Deterministic WhatsApp routing for appointment and human-agent requests on social DMs.

Normal Instagram/Facebook messages must reach the canonical Linas AI. This module only
intercepts after an explicit booking/human-agent (or tattoo-removal contact) intent, then
collects missing branch/gender one field at a time before returning a WhatsApp handoff.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
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


def _flow_scope(user_data: dict) -> SocialContactScope:
    tenant_id = str(user_data.get("tenant_id") or user_data.get("workspace_id") or "").strip()
    channel = str(user_data.get("channel") or "").strip().lower()
    business_asset_id = str(user_data.get("meta_account_id") or "").strip()
    sender_id = str(user_data.get("social_sender_id") or "").strip()
    if not tenant_id or channel not in SOCIAL_CHANNELS or not business_asset_id or not sender_id:
        raise SocialContactScopeError("Social handoff scope is incomplete")
    return SocialContactScope(
        tenant_id=tenant_id,
        channel=channel,
        business_asset_id=business_asset_id,
        sender_id=sender_id,
    )


def _scope_fingerprint(scope: SocialContactScope) -> str:
    components = (
        scope.tenant_id,
        scope.channel,
        scope.business_asset_id,
        scope.sender_id,
    )
    framed = "".join(f"{len(component)}:{component}" for component in components)
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def social_booking_preference_key(user_data: dict) -> str:
    """Stable opaque key for one social customer's durable booking preference."""
    return _scope_fingerprint(_flow_scope(user_data))


def _preference_memory_key(user_data: dict) -> str:
    return f"{SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX}{social_booking_preference_key(user_data)}"


def get_social_booking_preference(user_data: dict) -> str | None:
    """Return the validated in-memory preference for the current social scope."""
    value = user_data.get(_preference_memory_key(user_data))
    return value if value in {"male", "female"} else None


def set_social_booking_preference(user_data: dict, preference: str) -> None:
    """Cache a validated durable preference without touching temporary flow state."""
    if preference not in {"male", "female"}:
        raise ValueError("Invalid social booking preference")
    user_data[_preference_memory_key(user_data)] = preference


def clear_social_booking_preference(user_data: dict) -> None:
    """Discard an in-memory preference when the durable profile write failed."""
    user_data.pop(_preference_memory_key(user_data), None)


def restore_social_booking_preference(user_data: dict, persisted_state: dict) -> str | None:
    """Restore only this exact social scope from the existing customer profile document."""
    stored_preferences = persisted_state.get(SOCIAL_BOOKING_PREFERENCES_FIELD)
    if not isinstance(stored_preferences, dict):
        return None
    record = stored_preferences.get(social_booking_preference_key(user_data))
    if not isinstance(record, dict):
        return None
    preference = record.get("value")
    if not isinstance(preference, str) or preference not in {"male", "female"}:
        return None
    set_social_booking_preference(user_data, preference)
    return preference


def _sender_fingerprint(sender_id: str) -> str:
    return hashlib.sha256(sender_id.encode("utf-8")).hexdigest()


def _flow_state_key(user_data: dict) -> str:
    """Key active handoff state by tenant, channel, business asset, and sender."""
    return f"social_contact_flow::v2::{_scope_fingerprint(_flow_scope(user_data))}"


def _purge_legacy_flow_state(user_data: dict) -> None:
    """Retire unsafe unscoped and pre-v2 flow blobs instead of migrating their fields."""
    user_data.pop("social_contact_flow", None)
    for key in list(user_data.keys()):
        if str(key).startswith("social_contact_flow::") and not str(key).startswith("social_contact_flow::v2::"):
            user_data.pop(key, None)


def _get_flow_state(user_data: dict) -> dict:
    _purge_legacy_flow_state(user_data)
    scope = _flow_scope(user_data)
    key = _flow_state_key(user_data)
    state = user_data.get(key)
    expected_fingerprint = key.rsplit("::", 1)[-1]
    if not isinstance(state, dict):
        return {}
    if (
        state.get("status") != "active"
        or state.get("intent") not in {"booking", "human"}
        or state.get("scope_fingerprint") != expected_fingerprint
        or state.get("tenant_id") != scope.tenant_id
        or state.get("channel") != scope.channel
        or state.get("business_asset_id") != scope.business_asset_id
        or state.get("sender_fingerprint") != _sender_fingerprint(scope.sender_id)
        or not isinstance(state.get("flow_id"), str)
        or not state.get("flow_id")
    ):
        user_data.pop(key, None)
        return {}
    return state


def _set_flow_state(user_data: dict, state: dict) -> None:
    scope = _flow_scope(user_data)
    key = _flow_state_key(user_data)
    state = dict(state)
    state["status"] = "active"
    state["scope_fingerprint"] = key.rsplit("::", 1)[-1]
    state["tenant_id"] = scope.tenant_id
    state["channel"] = scope.channel
    state["business_asset_id"] = scope.business_asset_id
    state["sender_fingerprint"] = _sender_fingerprint(scope.sender_id)
    state["updated_at"] = time.time()
    if "started_at" not in state:
        state["started_at"] = state["updated_at"]
    user_data[key] = state
    _purge_legacy_flow_state(user_data)


def _clear_flow_state(user_data: dict) -> None:
    _purge_legacy_flow_state(user_data)
    user_data.pop(_flow_state_key(user_data), None)


def _state_expired(state: dict) -> bool:
    """Expire after SOCIAL_CONTACT_FLOW_TTL_SECONDS of inactivity (updated_at)."""
    if not state:
        return False
    stamp = state.get("updated_at")
    if stamp is None:
        stamp = state.get("started_at")
    try:
        stamp_f = float(stamp or 0)
    except (TypeError, ValueError):
        return True
    return (time.time() - stamp_f) > SOCIAL_CONTACT_FLOW_TTL_SECONDS


def _is_valid_continuation(message: str, state: dict) -> bool:
    """Only branch/gender answers (or re-stated handoff intent) continue a pending flow."""
    if detect_branch(message):
        return True
    if _other_person_booking_gender(message):
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
    language: str | None = None,
    force_intent: str | None = None,
) -> SocialContactRouteResult | None:
    """Return a deterministic WhatsApp-handoff reply only for explicit social handoff flows.

    ``force_intent`` (from GPT/router) cannot start a new handoff by itself. A new flow
    starts only when the user message explicitly requests booking/human/tattoo contact.
    A branch must always come from the current explicit request or this same isolated
    active flow. A saved Men/Women booking preference may fill only the missing
    category after branch collection; it is scope-isolated and never copied into
    temporary handoff state.
    Pending branch/gender collection continues only on valid answers; greetings, cancels,
    topic changes, and expired state return None so the canonical AI handles the message.
    """
    explicit = _explicit_handoff_intent(message)
    try:
        state = _get_flow_state(user_data)
        saved_preference = get_social_booking_preference(user_data)
    except SocialContactScopeError:
        clear_social_contact_flow(user_data)
        if explicit:
            raise
        return None
    if state and _state_expired(state):
        _clear_flow_state(user_data)
        state = {}

    selected_gender, another_person_override = _message_gender_selection(message)
    explicit_preference_change = _explicit_preference_change(message)
    preference_to_persist: str | None = None

    # A direct preference change may happen outside a booking flow. It is the only
    # standalone social category message that produces a deterministic reply.
    if explicit_preference_change and selected_gender:
        if saved_preference != selected_gender:
            set_social_booking_preference(user_data, selected_gender)
            saved_preference = selected_gender
            preference_to_persist = selected_gender
        if not explicit and not state:
            return SocialContactRouteResult(
                reply="",
                intent="preference",
                gender=selected_gender,
                preference_to_persist=preference_to_persist,
            )

    if explicit:
        # A new user-authored booking/human request always replaces prior state.
        # Only fields present in this message may seed the new active flow.
        _clear_flow_state(user_data)
        state = {
            "flow_id": uuid.uuid4().hex,
            "status": "active",
            "intent": explicit,
            "started_at": time.time(),
        }
        if explicit == "human":
            # Owner inbox alert (Instagram/Facebook never enter waiting_human queue).
            try:
                from services.owner_alert_service import owner_alert_service

                scope_tenant = str(user_data.get("tenant_id") or user_data.get("tenantId") or "linas")
                scope_channel = str(user_data.get("channel") or "")
                try:
                    scope = _flow_scope(user_data)
                    scope_tenant = scope.tenant_id
                    scope_channel = scope.channel
                except SocialContactScopeError:
                    pass
                social_uid = str(user_data.get("user_id") or "").strip()
                if not social_uid:
                    phone = str(user_data.get("phone_number") or "")
                    if phone.startswith("room:"):
                        social_uid = phone[5:].strip()
                if not social_uid and user_data.get("social_sender_id"):
                    try:
                        from services.social_user_id import compose_social_user_id

                        social_uid = compose_social_user_id(
                            tenant_id=scope_tenant,
                            channel=scope_channel or "instagram",
                            asset_id=str(user_data.get("meta_account_id") or ""),
                            sender_id=str(user_data.get("social_sender_id") or ""),
                        )
                    except Exception:
                        social_uid = f"{scope_channel}:{user_data.get('social_sender_id')}"
                display_name = str(
                    user_data.get("user_name") or user_data.get("name") or user_data.get("profile_name") or ""
                )
                if not display_name and social_uid:
                    try:
                        import config as _cfg

                        display_name = str(_cfg.user_names.get(social_uid) or "")
                    except Exception:
                        display_name = ""
                owner_alert_service.emit_social_human_request(
                    tenant_id=scope_tenant,
                    customer_name=display_name,
                    user_id=social_uid or None,
                    conversation_id=str(user_data.get("current_conversation_id") or "") or None,
                    channel=scope_channel,
                    last_message=message,
                    trigger_source="social_explicit_human_request",
                )
            except Exception as alert_err:
                print(f"⚠️ social human owner alert failed: {alert_err}")

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

    state = (
        dict(state)
        if state
        else {
            "flow_id": uuid.uuid4().hex,
            "status": "active",
            "started_at": time.time(),
        }
    )
    state["intent"] = detected_intent

    detected_branch = detect_branch(message)
    if detected_branch:
        state["branch"] = detected_branch

    tattoo = bool(state.get("tattoo_removal")) or is_tattoo_removal_request(message)
    state["tattoo_removal"] = tattoo

    if selected_gender:
        state["gender"] = selected_gender
        if another_person_override:
            state["gender_source"] = "current_request_override"
        else:
            state["gender_source"] = "customer_selection"
            if saved_preference != selected_gender:
                set_social_booking_preference(user_data, selected_gender)
                saved_preference = selected_gender
                preference_to_persist = selected_gender
    state_gender = state.get("gender") if state.get("gender") in {"male", "female"} else None
    gender = state_gender or saved_preference

    lang = _language(language)
    _set_flow_state(user_data, state)

    if tattoo:
        # Confirmed clinic truth: tattoo removal is unsupported. Never return a WhatsApp number.
        reply = _unsupported_service_refuse_reply(lang)
        _clear_flow_state(user_data)
        return SocialContactRouteResult(
            reply,
            detected_intent,
            branch=None,
            gender=gender,
            contact_env=None,
            tattoo_removal=True,
            preference_to_persist=preference_to_persist,
        )

    branch = state.get("branch")
    if not branch:
        return SocialContactRouteResult(
            _ask_branch(lang),
            detected_intent,
            gender=gender,
            preference_to_persist=preference_to_persist,
        )
    if not gender:
        return SocialContactRouteResult(
            _ask_gender(lang),
            detected_intent,
            branch=branch,
            preference_to_persist=preference_to_persist,
        )

    env_name = f"SOCIAL_WHATSAPP_{branch.upper()}_{gender.upper()}"
    phone = resolve_social_whatsapp_number(
        env_name,
        tenant_id=str(user_data.get("tenant_id") or "linas"),
    )
    if not phone:
        return SocialContactRouteResult(
            _missing_contact(lang),
            detected_intent,
            branch=branch,
            gender=gender,
            contact_env=env_name,
            preference_to_persist=preference_to_persist,
        )

    reply = _laser_contact_reply(lang, branch, phone)
    _clear_flow_state(user_data)
    return SocialContactRouteResult(
        reply,
        detected_intent,
        branch=branch,
        gender=gender,
        contact_env=env_name,
        preference_to_persist=preference_to_persist,
    )


def expire_social_contact_flows_in_user_data(user_data: dict) -> int:
    """Clear expired/invalid social handoff blobs on a user_data dict. Returns cleared count."""
    cleared = 0
    for key in list(user_data.keys()):
        if key != "social_contact_flow" and not str(key).startswith("social_contact_flow::"):
            continue
        state = user_data.get(key)
        key_text = str(key)
        key_fingerprint = key_text.rsplit("::", 1)[-1]
        if (
            not key_text.startswith("social_contact_flow::v2::")
            or not isinstance(state, dict)
            or state.get("status") != "active"
            or state.get("intent") not in {"booking", "human"}
            or state.get("scope_fingerprint") != key_fingerprint
            or not isinstance(state.get("flow_id"), str)
            or not state.get("flow_id")
            or _state_expired(state)
        ):
            user_data.pop(key, None)
            cleared += 1
    return cleared


def reset_social_contact_flow_for_sender(user_data: dict) -> bool:
    """Reset pending handoff for the current channel/account scope only."""
    before = _get_flow_state(user_data)
    _clear_flow_state(user_data)
    return bool(before)
