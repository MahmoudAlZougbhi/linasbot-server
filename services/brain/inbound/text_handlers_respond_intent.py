"""Intent helpers still used by the published CM inbound path."""

from __future__ import annotations

import json
import re

from services.brain.inbound.text_handlers_respond_keywords import (
    ALLOWED_GENERAL_QUERIES,
    BUSINESS_SCOPE_KEYWORDS,
    GENERAL_QUESTION_PREFIX_RE,
    OFF_TOPIC_KEYWORDS,
    PRICE_INTENT_KEYWORDS,
)


def _is_price_intent(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in PRICE_INTENT_KEYWORDS)


def _is_out_of_business_scope_query(text: str) -> bool:
    probe = str(text or "").strip()
    if len(probe) < 3:
        return False

    lowered = probe.lower()

    if any(phrase in lowered for phrase in ALLOWED_GENERAL_QUERIES):
        return False

    if any(keyword in lowered for keyword in BUSINESS_SCOPE_KEYWORDS):
        return False

    if any(keyword in lowered for keyword in OFF_TOPIC_KEYWORDS):
        return True

    if GENERAL_QUESTION_PREFIX_RE.search(lowered) and len(lowered.split()) >= 3:
        return True

    return False


def _build_out_of_scope_reply(lang: str) -> str:
    messages = {
        "ar": "أنا مخصّصة فقط لخدمات هذا العمل المنشورة. فيني ساعدك بأي سؤال عن الخدمات، الأسعار، أو الطلبات.",
        "franco": "أنا مخصّصة فقط لخدمات هذا العمل المنشورة. فيني ساعدك بأي سؤال عن الخدمات، الأسعار، أو الطلبات.",
        "en": "I can only help with this business's published services, prices, and requests.",
        "fr": "Je peux uniquement aider concernant les services, prix et demandes publiés de cette entreprise.",
    }
    return messages.get((lang or "ar").lower(), messages["ar"])


def _unwrap_embedded_json_reply(text: str) -> str:
    """Unwrap nested {"action": "...", "bot_reply": "..."} so users only see text."""
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
