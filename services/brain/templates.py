"""Localized Brain customer-facing templates. Prefer CM dynamic messages when present."""

from __future__ import annotations

_HANDOFF = {
    "en": "I'll connect you with someone from the team shortly, and they'll be with you.",
    "ar": "رح حوّلك لحدا من الفريق شوي، وبيكون معك.",
    "fr": "Je vous mets en relation avec quelqu’un de l’équipe sous peu, et il sera avec vous.",
}
_CONFIRM = {
    "en": "I can help with that. Please confirm the details so I can submit the request.",
    "ar": "يمكنني المساعدة. يرجى تأكيد التفاصيل لأتمكن من إرسال الطلب.",
    "fr": "Je peux vous aider. Merci de confirmer les détails pour que je soumette la demande.",
}
_VISUAL_DISABLED = {
    "en": "I can’t read photos yet. Please describe what you need in text, or ask a teammate.",
    "ar": "لا أستطيع قراءة الصور بعد. صف ما تحتاجه نصاً أو اطلب مساعدة زميل.",
    "fr": "Je ne peux pas encore lire les photos. Décrivez votre besoin en texte, ou demandez à un collègue.",
}
_NO_EVIDENCE = {
    "en": "Sorry, I don’t have information about that question yet.",
    "ar": "آسف، ما عندي معلومات عن هالسؤال هلق.",
    "fr": "Désolé, je n’ai pas encore d’information sur cette question.",
}
_NO_EVIDENCE_HANDOFF = {
    "en": (
        "Sorry, I don’t have information about that question yet. "
        "I’ll connect you with someone from the team shortly, and they’ll be with you."
    ),
    "ar": "آسف، ما عندي معلومات عن هالسؤال هلق. رح حوّلك لحدا من الفريق شوي، وبيكون معك.",
    "fr": (
        "Désolé, je n’ai pas encore d’information sur cette question. "
        "Je vous mets en relation avec quelqu’un de l’équipe sous peu, et il sera avec vous."
    ),
}
_FAQ_AMBIGUOUS = {
    "en": "I found more than one matching FAQ. Please rephrase with more detail so I answer the right one.",
    "ar": "وجدت أكثر من سؤال شائع مطابق. أعد الصياغة بمزيد من التفاصيل لأجيب عن السؤال الصحيح.",
    "fr": "Plusieurs FAQ correspondent. Reformulez avec plus de détails pour que je réponde à la bonne.",
}


def _lang(code: str) -> str:
    raw = (code or "en").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("fr"):
        return "fr"
    return "en"


def owner_protocol_text(key: str, response_language: str = "") -> str:
    """Owner-authored dynamic message only. Empty when the tenant has no verbatim copy."""
    lang = _lang(response_language)
    mapped = {
        "handoff": "brain_handoff_ack",
        "confirm_request": "brain_confirm_request",
        "visual_disabled": "brain_visual_disabled",
        "no_evidence": "brain_no_evidence",
        "no_evidence_handoff": "brain_no_evidence_handoff",
        "faq_ambiguous": "brain_faq_ambiguous",
    }.get(key)
    if not mapped:
        return ""
    try:
        from services.owner_copilot.dynamic_messages_service import get_dynamic_message

        text = (get_dynamic_message(mapped, lang) or "").strip()
        if text and text != mapped:
            return text
    except Exception:
        pass
    return ""


def brain_template(key: str, response_language: str = "") -> str:
    owner = owner_protocol_text(key, response_language)
    if owner:
        return owner
    table = {
        "handoff": _HANDOFF,
        "confirm_request": _CONFIRM,
        "visual_disabled": _VISUAL_DISABLED,
        "no_evidence": _NO_EVIDENCE,
        "no_evidence_handoff": _NO_EVIDENCE_HANDOFF,
        "faq_ambiguous": _FAQ_AMBIGUOUS,
    }.get(key) or _NO_EVIDENCE
    lang = _lang(response_language)
    return table.get(lang) or table["en"]
