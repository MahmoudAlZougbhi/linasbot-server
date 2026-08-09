"""Context-aware first message / reopen greeting for System Copilot."""

from __future__ import annotations

from typing import Any

from services.owner_ai_account_state import resolve_setup_stage
from services.owner_ai_profile import address_line, normalize_language, read_owner_profile

_COPY: dict[str, dict[str, str]] = {
    "new": {
        "en": (
            "{hi}. I’m Linas AI — your System Copilot for the whole app. "
            "I can help configure Content Management, connect Meta, check usage, "
            "and prepare posts. Where would you like to start?"
        ),
        "ar": (
            "{hi}. أنا Linas AI — مساعد النظام لتطبيقك بالكامل. "
            "أساعدك في إعداد Content Management، وربط Meta، ومراجعة الاستخدام، "
            "وإعداد المنشورات. من أين نبدأ؟"
        ),
        "fr": (
            "{hi}. Je suis Linas AI — le copilote système de toute l’application. "
            "Je peux vous aider pour Content Management, Meta, l’usage et les publications. "
            "Par où commencer ?"
        ),
    },
    "cm_partial": {
        "en": (
            "{hi}. Your Content Management setup is partially complete. "
            "I can continue where you left off, or jump to integrations, usage, or creative work."
        ),
        "ar": (
            "{hi}. إعداد Content Management لديك مكتمل جزئياً. "
            "يمكنني المتابعة من حيث توقفت، أو الانتقال إلى التكاملات أو الاستخدام أو الإبداع."
        ),
        "fr": (
            "{hi}. Votre configuration Content Management est partielle. "
            "Je peux continuer, ou passer aux intégrations, à l’usage ou à la création."
        ),
    },
    "cm_ready_no_integration": {
        "en": (
            "{hi}. Your AI content looks ready — next useful step is connecting Meta "
            "so customers can reach you. I can also review usage or draft a post."
        ),
        "ar": (
            "{hi}. يبدو أن محتوى الذكاء الاصطناعي جاهز — الخطوة المفيدة التالية هي ربط Meta "
            "ليصل إليك العملاء. يمكنني أيضاً مراجعة الاستخدام أو إعداد منشور."
        ),
        "fr": (
            "{hi}. Votre contenu IA semble prêt — l’étape utile suivante est de connecter Meta. "
            "Je peux aussi vérifier l’usage ou préparer une publication."
        ),
    },
    "fully_configured": {
        "en": (
            "{hi}. Welcome back. Everything core looks configured — ask me about usage, "
            "scheduled posts, Content Management tweaks, or creative work."
        ),
        "ar": (
            "{hi}. أهلاً بعودتك. الإعداد الأساسي يبدو مكتملاً — اسألني عن الاستخدام، "
            "المنشورات المجدولة، تعديلات Content Management، أو العمل الإبداعي."
        ),
        "fr": (
            "{hi}. Bon retour. L’essentiel semble configuré — demandez-moi l’usage, "
            "les publications planifiées, des ajustements CM ou du contenu créatif."
        ),
    },
}

_ADDRESS_PROMPT: dict[str, str] = {
    "en": " How should I address you?",
    "ar": " كيف تفضّل أن أناديك؟",
    "fr": " Comment souhaitez-vous que je m’adresse à vous ?",
}


def build_greeting(
    *,
    tenant_id: str,
    user_id: str,
    language: str | None = None,
    include_address_prompt: bool = True,
) -> dict[str, Any]:
    profile = read_owner_profile(user_id)
    lang = normalize_language(language or profile.get("preferred_language"), fallback="en")
    stage = resolve_setup_stage(tenant_id)
    hi = address_line(profile, language=lang)
    template = _COPY.get(stage, _COPY["new"]).get(lang) or _COPY["new"]["en"]
    text = template.format(hi=hi)
    asked = bool(profile.get("address_prompt_asked"))
    has_name = bool(profile.get("display_name") or profile.get("form_of_address"))
    if include_address_prompt and not asked and not has_name:
        text += _ADDRESS_PROMPT.get(lang, _ADDRESS_PROMPT["en"])
    return {
        "text": text,
        "setup_stage": stage,
        "language": lang,
        "address_prompt_included": include_address_prompt and not asked and not has_name,
        "gender": profile.get("gender") or "unset",
    }
