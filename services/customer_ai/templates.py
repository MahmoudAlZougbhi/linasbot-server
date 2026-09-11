"""Localized Brain customer-facing templates. Prefer CM dynamic messages when present."""

from __future__ import annotations


_HANDOFF = {
    "en": "A teammate will continue from here.",
    "ar": "سيكمل أحد الزملاء من هنا.",
    "fr": "Un collègue va continuer à partir d’ici.",
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
    "en": "I don’t have published information for that yet. Please rephrase or ask a teammate.",
    "ar": "لا تتوفر معلومات منشورة عن ذلك بعد. أعد الصياغة أو اطلب مساعدة زميل.",
    "fr": "Je n’ai pas encore d’information publiée à ce sujet. Reformulez ou demandez à un collègue.",
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


def brain_template(key: str, response_language: str = "") -> str:
    table = {
        "handoff": _HANDOFF,
        "confirm_request": _CONFIRM,
        "visual_disabled": _VISUAL_DISABLED,
        "no_evidence": _NO_EVIDENCE,
        "faq_ambiguous": _FAQ_AMBIGUOUS,
    }.get(key) or _NO_EVIDENCE
    lang = _lang(response_language)
    try:
        from services.dynamic_messages_service import get_dynamic_message

        mapped = {
            "handoff": "brain_handoff_ack",
            "confirm_request": "brain_confirm_request",
            "visual_disabled": "brain_visual_disabled",
            "no_evidence": "brain_no_evidence",
            "faq_ambiguous": "brain_faq_ambiguous",
        }.get(key)
        if mapped:
            text = (get_dynamic_message(mapped, lang) or "").strip()
            if text and text != mapped:
                return text
    except Exception:
        pass
    return table.get(lang) or table["en"]
