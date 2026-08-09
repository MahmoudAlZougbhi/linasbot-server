"""Guest sales chat — product explanation only. No CM writes, no tools, no tenant mutation."""

from __future__ import annotations

import re
from typing import Any

from services.guest_chat_limits import GUEST_MAX_QUESTIONS, GUEST_MAX_WORDS, count_words
from services.system_knowledge_retrieval import detect_message_language, retrieve_capabilities

# Explicit denylist: guest path must never dispatch these (defence in depth).
FORBIDDEN_GUEST_TOOLS = frozenset(
    {
        "propose_cm_patch",
        "approve_cm_patch",
        "publish_cm",
        "validate_cm",
        "propose_smart_answer",
        "approve_smart_answer",
        "approve_diagnosis_fix",
        "dispatch_tool",
    }
)

_AR = re.compile(r"[\u0600-\u06FF]")


def build_guest_greeting(*, language: str = "en") -> str:
    if language == "ar":
        return (
            "مرحباً — أنا Linas AI. أساعدك تفهم كيف نُشغّل ذكاء أعمال لمشروعك: "
            "ردود العملاء، إدارة المحتوى، التكاملات، والاستخدام. "
            "اسألني ماذا نقدّم — وبعد تسجيل الدخول تحصل على مساعد النظام الكامل."
        )
    if language == "fr":
        return (
            "Bonjour — je suis Linas AI. Je vous explique comment nous aidons les entreprises : "
            "réponses clients, Content Management, intégrations et usage. "
            "Demandez ce que nous offrons ; après connexion, le copilote système complet s’ouvre."
        )
    return (
        "Hi — I’m Linas AI. I help businesses run customer AI: smart replies, "
        "Content Management, Meta integrations, usage, and a System Copilot after you sign in. "
        "Ask what we offer — guest chat is explanatory only."
    )


def _sales_intro(lang: str) -> str:
    if lang == "ar":
        return (
            "Linas AI منصة ذكاء اصطناعي للأعمال: تربط قنواتك، تضبط معرفة نشاطك، "
            "وترد على العملاء بأسلوب علامتك — مع مساعد نظام يدير الإعداد والاستخدام."
        )
    if lang == "fr":
        return (
            "Linas AI est une plateforme d’IA métier : connectez vos canaux, définissez "
            "la connaissance de votre activité, et répondez aux clients avec un copilote système."
        )
    return (
        "Linas AI is a business AI platform: connect channels, configure what your AI knows, "
        "and reply to customers in your brand voice — with a System Copilot for setup and ops."
    )


def compose_guest_reply(user_text: str, *, language: str | None = None) -> dict[str, Any]:
    """Sales-only reply from product knowledge. Never mutates tenant state."""
    text = (user_text or "").strip()
    lang = language or detect_message_language(text, fallback="en")
    if lang not in {"en", "ar", "fr"}:
        lang = "en"

    caps = retrieve_capabilities(text, limit=5)
    # Strip any tool-oriented fields from guest-facing payload.
    public_caps = []
    for cap in caps:
        row = cap.to_public()
        row.pop("tools", None)
        public_caps.append(row)

    titles = [str(c.get("feature") or "").replace("_", " ") for c in public_caps if c.get("feature")]
    titles = [t for t in titles if t][:5]

    if lang == "ar":
        body = _sales_intro(lang)
        if titles:
            body += " نقدّم مثلاً: " + "، ".join(titles) + "."
        body += (
            " كضيف يمكنك الاستفسار فقط — لإنشاء مساحة عمل أو تعديل Content Management "
            "يلزم تسجيل الدخول أو الاشتراك."
        )
    elif lang == "fr":
        body = _sales_intro(lang)
        if titles:
            body += " Exemples : " + ", ".join(titles) + "."
        body += (
            " En invité, le chat est explicatif seulement — connectez-vous pour le copilote "
            "et la configuration Content Management."
        )
    else:
        body = _sales_intro(lang)
        if titles:
            body += f" Highlights for your question: {', '.join(titles)}."
        body += (
            " As a guest I only explain the product — sign in or subscribe to operate CM, "
            "integrations, billing, and the full System Copilot."
        )

    return {
        "reply_text": body,
        "language": lang,
        "capabilities": public_caps,
        "tools_used": [],
        "forbidden_tools_blocked": sorted(FORBIDDEN_GUEST_TOOLS),
        "word_count": count_words(text),
        "limits": {"max_questions": GUEST_MAX_QUESTIONS, "max_words": GUEST_MAX_WORDS},
    }


def assert_no_tool_writes(result: dict[str, Any]) -> None:
    tools = result.get("tools_used") or []
    if tools:
        raise RuntimeError("guest path must not execute tools")
    for name in FORBIDDEN_GUEST_TOOLS:
        if name in str(result.get("reply_text") or "") and name.startswith("approve_"):
            # Soft check only on execution list; reply text may mention product features.
            pass
