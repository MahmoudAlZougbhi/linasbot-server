"""Guest sales chat — product explanation only. No CM writes, no tools, no tenant mutation."""

from __future__ import annotations

import os
from typing import Any

from services.guest_chat_limits import (
    GUEST_MAX_INPUT_TOKENS,
    GUEST_MAX_QUESTIONS,
    GUEST_MAX_WORDS,
    count_words,
)
from services.model_policy import MODEL_OWNER_SOL
from services.response_formatting import RESPONSE_FORMATTING_RULES
from services.system_knowledge_retrieval import (
    capabilities_as_prompt_block,
    detect_message_language,
    retrieve_capabilities,
)
from services.welcome_pool import pick_welcome

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

MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 700
# V2: guest product explainer on Sol + low reasoning (text-only, no tools).
DEFAULT_GUEST_MODEL = MODEL_OWNER_SOL
GUEST_REASONING_EFFORT = "low"


class GuestAIModelError(RuntimeError):
    """Raised when the guest sales model is unavailable or returns an empty reply.

    No canned sales fallback — callers must surface an honest error to the client.
    """


def guest_model_name() -> str:
    return (os.getenv("LINAS_GUEST_MODEL") or DEFAULT_GUEST_MODEL).strip() or DEFAULT_GUEST_MODEL


_GUEST_HI = {"ar": "مرحباً", "fr": "Bonjour", "en": "Hello"}


def build_guest_greeting(*, language: str = "en", session_id: str = "guest") -> str:
    lang = language if language in _GUEST_HI else "en"
    return pick_welcome(
        language=lang,
        user_key=f"guest:{session_id}",
        hi=_GUEST_HI[lang],
    )


def _trim(text: str, limit: int = MAX_HISTORY_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _product_primer(lang: str) -> str:
    if lang == "ar":
        return (
            "Linas AI منصة ذكاء اصطناعي للأعمال: تربط قنواتك، تضبط معرفة نشاطك عبر إعداد الذكاء الاصطناعي، "
            "وترد على العملاء بأسلوب علامتك، مع System Copilot داخل التطبيق بعد الاشتراك."
        )
    if lang == "fr":
        return (
            "Linas AI est une plateforme d’IA métier : canaux, Configuration IA (ce que l’IA sait), "
            "réponses clients dans la voix de la marque, et System Copilot dans l’app après abonnement."
        )
    return (
        "Linas AI is a business AI platform focused on Instagram/Facebook DMs and comments: "
        "connect channels, configure AI Setup, and use System Copilot in the app after signup. "
        "Creative Studio / social post generation is not part of the current product."
    )


def build_guest_system_prompt(*, language: str, knowledge_block: str) -> str:
    lang = language if language in {"en", "ar", "fr"} else "en"
    return (
        "You are Linas AI — a warm, friendly, clear product explainer for the Linas AI app.\n"
        "Speak like a helpful expert and approachable colleague, not a brochure or a broken record.\n"
        "Voice: use tasteful emojis naturally (especially in Arabic / Lebanese-friendly tone); never spam or clown.\n"
        "Stay professional enough for business questions; friendly ≠ silly.\n"
        "Answer THIS user's question directly; vary wording every turn; use conversation history for follow-ups.\n"
        "Do not force a download/subscribe pitch into every answer. Mention signup only when relevant.\n"
        "SCOPE (hard): explain ONLY Linas AI the product — features, setup flow, Meta channels, "
        "AI Setup / Content Manager concepts, billing/subscribe high-level, and how the app works.\n"
        "You are NOT a general-purpose chatbot and NOT a tenant business support bot "
        "(no clinic/salon/shop hours, prices, bookings, or pretending you know a customer's business).\n"
        "You have NO tenant Content Manager knowledge and must not invent business-specific facts.\n"
        "If asked for a specific business's services/prices/hours, say that lives in their own "
        "AI Setup after they subscribe — you only explain the product.\n"
        "Guest constraints (hard): no tools, no CM writes, no tenant mutation, no claiming you changed anything.\n"
        "Do not invent live Meta comment automation, verified publish, or store IAP if knowledge marks them gated/partial.\n"
        "Creative posts/images/videos are out of scope — say so briefly if asked.\n"
        "If you don't know a detail, say so honestly.\n"
        f"Reply language: match the user's language automatically (multilingual by default). "
        f"Understand Arabizi/Franco but never reply in Arabizi — use Arabic script for Arabic. "
        f"Current hint language: {lang}.\n"
        "Keep replies useful; expand when the user asks for detail.\n"
        f"{RESPONSE_FORMATTING_RULES}\n"
        f"Product primer: {_product_primer(lang)}\n"
        f"{knowledge_block or 'Relevant capabilities: general Linas AI product overview.'}"
    )


def history_to_chat_messages(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Convert stored guest turns into OpenAI chat messages (roles user/assistant only)."""
    out: list[dict[str, str]] = []
    for item in history or []:
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = _trim(str(item.get("content") or ""))
        if not content:
            continue
        out.append({"role": role, "content": content})
    if len(out) > MAX_HISTORY_MESSAGES:
        out = out[-MAX_HISTORY_MESSAGES:]
    return out


def public_capabilities_for_query(user_text: str, *, limit: int = 5) -> list[dict[str, Any]]:
    caps = retrieve_capabilities(user_text, limit=limit)
    public_caps: list[dict[str, Any]] = []
    for cap in caps:
        row = cap.to_public()
        row.pop("tools", None)
        public_caps.append(row)
    return public_caps


async def compose_guest_reply(
    user_text: str,
    *,
    language: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """LLM sales reply grounded in product knowledge + session history. Never mutates tenant state."""
    text = (user_text or "").strip()
    if not text:
        raise GuestAIModelError("empty_guest_question")

    lang = language or detect_message_language(text, fallback="en")
    if lang not in {"en", "ar", "fr"}:
        lang = "en"

    caps = retrieve_capabilities(text, limit=5)
    knowledge_block = capabilities_as_prompt_block(caps)
    public_caps = public_capabilities_for_query(text, limit=5)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_guest_system_prompt(language=lang, knowledge_block=knowledge_block)},
        *history_to_chat_messages(history),
        {"role": "user", "content": text},
    ]

    model = guest_model_name()
    try:
        from services.llm_core_service import create_chat_completion, sanitize_llm_error

        response = await create_chat_completion(
            model=model,
            messages=messages,
            max_tokens=900,
            temperature=0.65,
            reasoning_effort=GUEST_REASONING_EFFORT,
        )
    except Exception as exc:  # noqa: BLE001 — surface provider/network failures honestly
        raise GuestAIModelError(f"guest_llm_unavailable:{type(exc).__name__}:{sanitize_llm_error(exc)}") from exc

    reply = ""
    try:
        reply = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise GuestAIModelError(f"guest_llm_bad_response:{type(exc).__name__}") from exc

    if not reply:
        finish = None
        try:
            finish = getattr(response.choices[0], "finish_reason", None)
        except Exception:  # noqa: BLE001
            finish = None
        raise GuestAIModelError(f"guest_llm_empty_reply:finish={finish}")

    usage = getattr(response, "usage", None)
    return {
        "reply_text": reply,
        "language": lang,
        "capabilities": public_caps,
        "tools_used": [],
        "forbidden_tools_blocked": sorted(FORBIDDEN_GUEST_TOOLS),
        "word_count": count_words(text),
        "limits": {
            "max_questions": GUEST_MAX_QUESTIONS,
            "max_words": GUEST_MAX_WORDS,
            "max_input_tokens": GUEST_MAX_INPUT_TOKENS,
        },
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def assert_no_tool_writes(result: dict[str, Any]) -> None:
    tools = result.get("tools_used") or []
    if tools:
        raise RuntimeError("guest path must not execute tools")
    for name in FORBIDDEN_GUEST_TOOLS:
        if name in str(result.get("reply_text") or "") and name.startswith("approve_"):
            # Soft check only on execution list; reply text may mention product features.
            pass
