"""Reply shaping, handover wording, and published CM runtime."""

from __future__ import annotations

import re
from typing import Any

from handlers.text_handlers_respond_intent import (
    _clean_reply_text,
    _looks_like_greeting_unit,
    _strip_leading_greeting_phrase,
)
from handlers.text_handlers_respond_keywords import (
    ASK_ONE_BY_ONE_ACTIONS,
    BRIEF_REPLY_ACTIONS,
    INTERROGATIVE_PREFIXES,
)


def _strip_redundant_greeting_prefix(reply_text: str) -> str:
    """
    Remove a leading greeting sentence when the turn is not eligible for greeting.
    Keeps original order and only strips the first greeting-like unit when there is
    enough remaining content.
    """
    cleaned = _clean_reply_text(reply_text)
    units = _split_reply_units(cleaned)
    if units and _looks_like_greeting_unit(units[0]):
        first_unit_wo_greeting = _strip_leading_greeting_phrase(units[0])
        if first_unit_wo_greeting and first_unit_wo_greeting != units[0]:
            rebuilt = " ".join([first_unit_wo_greeting] + units[1:]).strip()
            if len(rebuilt) >= 20:
                return rebuilt

        if len(units) >= 2:
            remaining = " ".join(units[1:]).strip()
            if len(remaining) >= 20:
                return remaining

    fallback = _strip_leading_greeting_phrase(cleaned)
    if fallback != cleaned and len(fallback) >= 20:
        return fallback
    return cleaned

def _split_reply_units(text: str) -> list:
    cleaned = _clean_reply_text(text)
    if not cleaned:
        return []
    units = re.split(r"(?:\n+|(?<=[.!؟?])\s+)", cleaned)
    out = []
    for unit in units:
        unit = re.sub(r"^\s*(?:\d+[.)]|[0-9]+️⃣|[-*•])\s*", "", unit.strip())
        if unit:
            out.append(unit)
    return out

def _looks_like_question(unit: str) -> bool:
    probe = str(unit or "").strip()
    if not probe:
        return False
    if "؟" in probe or "?" in probe:
        return True
    lowered = probe.lower()
    return lowered.startswith(INTERROGATIVE_PREFIXES)

def _truncate_chars(text: str, max_chars: int) -> str:
    content = str(text or "").strip()
    if len(content) <= max_chars:
        return content
    trimmed = content[: max_chars - 1].rstrip()
    return f"{trimmed}…"

def _apply_turn_by_turn_policy(action: str, bot_reply: str, lang: str) -> str:
    """
    Enforce concise turn-by-turn messaging:
    - Ask actions: one short question only
    - Answer actions: concise answer (max one follow-up question)
    """
    cleaned = _clean_reply_text(bot_reply)
    if not cleaned:
        return cleaned

    action = str(action or "").strip().lower()
    units = _split_reply_units(cleaned)
    if not units:
        return cleaned

    if action in ASK_ONE_BY_ONE_ACTIONS:
        question_unit = next((u for u in units if _looks_like_question(u)), units[0])
        question_unit = _truncate_chars(question_unit, 220)
        if lang in ("ar", "franco") and ("؟" not in question_unit and "?" not in question_unit):
            question_unit = f"{question_unit}؟"
        return question_unit

    if action in BRIEF_REPLY_ACTIONS:
        looks_verbose = (
            len(cleaned) > 320 or len(units) > 3 or bool(re.search(r"(?:^|\n)\s*(?:\d+[.)]|[0-9]+️⃣|[-*•])\s*", cleaned))
        )
        if not looks_verbose:
            return cleaned

        first_info_index = next(
            (idx for idx, unit in enumerate(units) if not _looks_like_question(unit)),
            None,
        )

        # If everything looks like a question, keep the first one only.
        if first_info_index is None:
            return _truncate_chars(units[0], 220)

        info_unit = _truncate_chars(units[first_info_index], 180)

        # Prefer a follow-up question that appears AFTER the selected info sentence
        # so we preserve natural order and avoid reversed output.
        question_unit = next(
            (unit for idx, unit in enumerate(units) if idx > first_info_index and _looks_like_question(unit)),
            "",
        )

        if question_unit:
            question_unit = _truncate_chars(question_unit, 140)
            combined = f"{info_unit} {question_unit}".strip()
            return _truncate_chars(combined, 320)

        # If no trailing question exists, allow a short leading greeting question (same order).
        leading_question = next(
            (unit for idx, unit in enumerate(units[:first_info_index]) if _looks_like_question(unit)),
            "",
        )
        if leading_question and first_info_index <= 1:
            combined = f"{_truncate_chars(leading_question, 140)} {info_unit}".strip()
            return _truncate_chars(combined, 320)

        return info_unit

    return cleaned

def _user_explicitly_requests_human_agent(text: str) -> bool:
    """True if the current user message clearly asks to speak with a person (not inferred from history)."""
    if not text or not str(text).strip():
        return False
    m = str(text).lower()
    needles = (
        "human",
        "agent",
        "person",
        "staff",
        "representative",
        "operator",
        "speak to",
        "talk to someone",
        "real person",
        "live agent",
        "customer service",
        "advisor",
        "supervisor",
        "موظف",
        "شخص",
        "بشري",
        "حد بشري",
        "خدمة العملاء",
        "بدي حدا",
        "بدي موظف",
        "بدي اتكلم",
        "مدير",
    )
    return any(n in m for n in needles)

def _reply_offers_handover_confirmation(text: str) -> bool:
    """True when the AI reply asks permission before connecting the user to staff."""
    if not text or not str(text).strip():
        return False
    m = str(text).lower()
    permission_markers = (
        "إذا بتحب",
        "اذا بتحب",
        "إذا بتحبي",
        "اذا بتحبي",
        "إذا حابب",
        "اذا حابب",
        "إذا حابة",
        "اذا حابة",
        "بدك",
        "would you like",
        "do you want me to",
        "if you want",
        "si vous voulez",
        "souhaitez-vous",
    )
    handover_markers = (
        "الفريق",
        "موظف",
        "اختصاصية",
        "يتواصل",
        "يتواصلوا",
        "أوصلك",
        "اوصلك",
        "أحولك",
        "احولك",
        "أحيل",
        "احيل",
        "connect you",
        "transfer you",
        "team contact",
        "specialist",
        "staff",
        "mettre en relation",
        "équipe",
        "specialiste",
        "spécialiste",
    )
    return any(p in m for p in permission_markers) and any(h in m for h in handover_markers)

async def _handle_published_cm_runtime(
    *,
    tenant_id: str,
    message: str,
    detected_language: str,
    response_language: str,
    user_id: str | None = None,
    conversation_id: str | None = None,
    channel: str | None = None,
    asset_id: str | None = None,
    provider_display_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run Customer Reply AI V2 end-to-end and return ``(reply_text, metadata)``.

    V2 is the sole generative engine for customer IG/FB DMs after existing gates.
    Never falls back to Classic ``generate_answer_with_usage``. On model/config
    failure, returns a safe closed failure reply with an explicit blocker.
    """
    from services.cm.constants import ANSWER_VALIDATION_FAILED_MESSAGE_KEY
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.dynamic_messages_service import get_dynamic_message

    social_channel = "instagram_dm"
    ch = (channel or "").strip().lower()
    if "facebook" in ch or ch in {"messenger", "page"}:
        social_channel = "facebook_dm"
    elif "instagram" in ch:
        social_channel = "instagram_dm"

    try:
        v2_outcome = await run_customer_reply_v2_dm(
            tenant_id=tenant_id,
            message=message,
            detected_language=detected_language,
            response_language=response_language,
            channel=social_channel,
            asset_id=asset_id or "",
            provider_sender_id=user_id or "",
            provider_display_name=provider_display_name or "",
            user_id=user_id or "",
            conversation_id=conversation_id or "",
        )
    except Exception as v2_exc:
        print(f"[_handle_published_cm_runtime] ⚠️ customer_reply_v2 failed closed: {v2_exc}")
        safe = get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, response_language)
        return safe, {
            "reason": "v2_failed_closed",
            "customer_reply_ai_v2": True,
            "classic_fallback": False,
            "blocker": str(v2_exc)[:200],
            "ai_called": False,
            "cost_status": "none",
            "pipeline_decisions": [
                {"step": "customer_reply_v2", "decision": "failed_closed", "ai_called": False},
            ],
        }

    reply = (v2_outcome.reply or "").strip()
    if not reply:
        reply = get_dynamic_message(ANSWER_VALIDATION_FAILED_MESSAGE_KEY, response_language)
    meta = {
        "reason": v2_outcome.reason or "v2_generated",
        "customer_reply_ai_v2": True,
        "classic_fallback": False,
        "v2_evidence_status": v2_outcome.evidence_status,
        "ai_called": True,
        "cost_status": "estimated",
        **(v2_outcome.metadata or {}),
        "pipeline_decisions": [
            {
                "step": "customer_reply_v2",
                "decision": v2_outcome.reason or "v2_generated",
                "ai_called": True,
            },
        ],
    }
    if v2_outcome.error:
        meta["blocker"] = str(v2_outcome.error)[:200]
    return reply, meta

