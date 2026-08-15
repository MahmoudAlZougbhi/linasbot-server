"""Customer-facing AI limit copy: which cap, and when it resets."""

from __future__ import annotations

from datetime import datetime

from services.ai_usage_limits_settings import period_reset_at, utc_now

_PERIOD_LABEL = {
    "en": {"day": "daily", "week": "weekly", "month": "monthly"},
    "ar": {"day": "اليومي", "week": "الأسبوعي", "month": "الشهري"},
    "fr": {"day": "quotidienne", "week": "hebdomadaire", "month": "mensuelle"},
    "franco": {"day": "daily", "week": "weekly", "month": "monthly"},
}

_KIND_EN = {
    "reply": "AI reply",
    "image": "photo analysis",
    "voice": "voice",
    "words": "text",
    "photos_message": "photo",
}

_KIND_AR = {
    "reply": "ردود الذكاء الاصطناعي",
    "image": "تحليل الصور",
    "voice": "الصوت",
    "words": "النص",
    "photos_message": "الصور",
}

_KIND_FR = {
    "reply": "réponses IA",
    "image": "analyse photo",
    "voice": "voix",
    "words": "texte",
    "photos_message": "photo",
}


def _lang(raw: str | None) -> str:
    key = (raw or "en").strip().lower()
    if key in {"ar", "franco"}:
        return "ar" if key == "ar" else "franco"
    if key.startswith("ar"):
        return "ar"
    if key.startswith("fr"):
        return "fr"
    return "en"


def format_reset_at(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M UTC")


def reset_iso(period: str, now: datetime | None = None) -> str:
    return period_reset_at(period, now).isoformat()


def customer_window_limit_message(
    *,
    kind: str,
    period: str,
    lang: str | None = None,
    now: datetime | None = None,
) -> str:
    code = _lang(lang)
    reset = format_reset_at(period_reset_at(period, now or utc_now()))
    period_key = period if period in {"day", "week", "month"} else "day"
    if code == "ar":
        kind_ar = _KIND_AR.get(kind, "الاستخدام")
        label = _PERIOD_LABEL["ar"][period_key]
        return f"وصلت إلى الحد {label} لـ{kind_ar}. تقدر تتواصل مع وكيلنا الذكي مرة ثانية بعد {reset}."
    if code == "fr":
        kind_fr = _KIND_FR.get(kind, "usage IA")
        label = _PERIOD_LABEL["fr"][period_key]
        return (
            f"Vous avez atteint la limite {label} de {kind_fr}. "
            f"Vous pourrez à nouveau joindre notre agent IA après {reset}."
        )
    if code == "franco":
        kind_en = _KIND_EN.get(kind, "AI")
        label = _PERIOD_LABEL["en"][period_key]
        return f"Wesselt 3al {label} {kind_en} limit. Fik terja3 la AI agent ba3d {reset}."
    kind_en = _KIND_EN.get(kind, "AI")
    label = _PERIOD_LABEL["en"][period_key]
    return f"You've reached the {label} {kind_en} limit. You can reach our AI agent again after {reset}."


def customer_words_truncated_message(*, word_limit: int, lang: str | None = None) -> str:
    code = _lang(lang)
    n = max(0, int(word_limit))
    if code == "ar":
        return f"ما قدرت أقرأ الرسالة كلها — فقط أول {n} كلمة كما هو مضبوط. ردي مبني على هذا الجزء."
    if code == "fr":
        return (
            f"Je n'ai pas pu tout lire — seulement les {n} premiers mots, comme configuré. "
            "Ma réponse se base sur cette partie."
        )
    if code == "franco":
        return f"Ma ederet e2ra kel el message — bass awwal {n} kelme. El jawab 3ala hayda l jize."
    return f"I couldn't read everything — only the first {n} words as configured. My reply is based on that part."


def customer_photos_truncated_message(*, photo_limit: int, lang: str | None = None) -> str:
    code = _lang(lang)
    n = max(0, int(photo_limit))
    if code == "ar":
        return f"حللت أول {n} صور فقط من هذه الرسالة، كما هو مضبوط."
    if code == "fr":
        return f"Je n'ai analysé que les {n} premières photos de ce message, comme configuré."
    if code == "franco":
        return f"Hallalt bass awwal {n} suwar men hayda l message."
    return f"I only analyzed the first {n} photos in this message, as configured."


def customer_voice_truncated_message(*, minute_limit: int, lang: str | None = None) -> str:
    code = _lang(lang)
    n = max(0, int(minute_limit))
    if code == "ar":
        return f"عالجت أول {n} دقيقة فقط من الرسالة الصوتية، كما هو مضبوط."
    if code == "fr":
        return f"Je n'ai traité que les {n} premières minutes de ce message vocal, comme configuré."
    if code == "franco":
        return f"3amalt process bass awwal {n} da2i2a men el voice note."
    return f"I only processed the first {n} minutes of this voice note, as configured."
