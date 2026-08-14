"""Owner-configured per-customer AI usage knobs (CM ai_limits → enforcement cache)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

RECOMMENDED_IMAGE_PER_DAY = 5
RECOMMENDED_IMAGE_PER_WEEK = 20
RECOMMENDED_IMAGE_PER_MONTH = 60
RECOMMENDED_PHOTOS_PER_MESSAGE = 2
RECOMMENDED_TEXT_WORDS_PER_MESSAGE = 500
RECOMMENDED_TEXT_REPLIES_PER_DAY = 20
RECOMMENDED_TEXT_REPLIES_PER_WEEK = 100
RECOMMENDED_TEXT_REPLIES_PER_MONTH = 300
RECOMMENDED_VOICE_MINUTES_PER_MESSAGE = 2
RECOMMENDED_VOICE_MINUTES_PER_DAY = 10
RECOMMENDED_VOICE_MINUTES_PER_WEEK = 40
RECOMMENDED_VOICE_MINUTES_PER_MONTH = 120
RECOMMENDED_CONTEXT_LINES_PER_DAY = 500
RECOMMENDED_CONTEXT_LINES_PER_WEEK = 2000

_HARD_MAX_IMAGES = 100_000
_HARD_MAX_LINES = 1_000_000
_HARD_MAX_REPLIES = 100_000
_HARD_MAX_MINUTES = 10_000
_HARD_MAX_WORDS = 100_000
_HARD_MAX_PHOTOS_MSG = 50

CUSTOMER_IMAGE_LIMIT_MESSAGE = (
    "You've reached this customer's photo-analysis limit. You can send photos to our AI agent again after the limit resets."
)
CUSTOMER_CONTEXT_LIMIT_MESSAGE = (
    "I can still help with a shorter question. Please send a brief message about what you need."
)
CUSTOMER_REPLY_LIMIT_MESSAGE = (
    "You've reached this customer's AI reply limit. You can reach our AI agent again after the limit resets."
)
CUSTOMER_VOICE_LIMIT_MESSAGE = (
    "You've reached this customer's voice limit. You can send voice notes to our AI agent again after the limit resets."
)


@dataclass(frozen=True)
class AiLimitSettings:
    unlimited: bool = False
    image_per_day: int = RECOMMENDED_IMAGE_PER_DAY
    image_per_week: int = RECOMMENDED_IMAGE_PER_WEEK
    image_per_month: int = RECOMMENDED_IMAGE_PER_MONTH
    photos_per_message: int = RECOMMENDED_PHOTOS_PER_MESSAGE
    text_words_per_message: int = RECOMMENDED_TEXT_WORDS_PER_MESSAGE
    text_replies_per_day: int = RECOMMENDED_TEXT_REPLIES_PER_DAY
    text_replies_per_week: int = RECOMMENDED_TEXT_REPLIES_PER_WEEK
    text_replies_per_month: int = RECOMMENDED_TEXT_REPLIES_PER_MONTH
    voice_minutes_per_message: int = RECOMMENDED_VOICE_MINUTES_PER_MESSAGE
    voice_minutes_per_day: int = RECOMMENDED_VOICE_MINUTES_PER_DAY
    voice_minutes_per_week: int = RECOMMENDED_VOICE_MINUTES_PER_WEEK
    voice_minutes_per_month: int = RECOMMENDED_VOICE_MINUTES_PER_MONTH
    context_lines_per_day: int = RECOMMENDED_CONTEXT_LINES_PER_DAY
    context_lines_per_week: int = RECOMMENDED_CONTEXT_LINES_PER_WEEK
    enforce_image_day: bool = True
    enforce_image_week: bool = True
    enforce_image_month: bool = True
    enforce_context_day: bool = True
    enforce_context_week: bool = True
    enforce_replies_day: bool = True
    enforce_replies_week: bool = True
    enforce_replies_month: bool = True
    enforce_voice_day: bool = True
    enforce_voice_week: bool = True
    enforce_voice_month: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "recommended": recommended_defaults(),
            "definitions": {
                "image": (
                    "Counts each photo the AI analyzes for one customer within the period, "
                    "across WhatsApp, Instagram, and Messenger."
                ),
                "reply": "Counts each AI reply that customer receives within the period.",
                "voice_minute": "Counts voice-note minutes the AI processes for that customer.",
                "text_words_per_message": "AI reads only the first N words of each inbound text message.",
                "photos_per_message": "AI analyzes only the first N photos in that inbound message.",
            },
        }


def recommended_defaults() -> dict[str, Any]:
    return {
        "unlimited": False,
        "image_per_day": RECOMMENDED_IMAGE_PER_DAY,
        "image_per_week": RECOMMENDED_IMAGE_PER_WEEK,
        "image_per_month": RECOMMENDED_IMAGE_PER_MONTH,
        "photos_per_message": RECOMMENDED_PHOTOS_PER_MESSAGE,
        "text_words_per_message": RECOMMENDED_TEXT_WORDS_PER_MESSAGE,
        "text_replies_per_day": RECOMMENDED_TEXT_REPLIES_PER_DAY,
        "text_replies_per_week": RECOMMENDED_TEXT_REPLIES_PER_WEEK,
        "text_replies_per_month": RECOMMENDED_TEXT_REPLIES_PER_MONTH,
        "voice_minutes_per_message": RECOMMENDED_VOICE_MINUTES_PER_MESSAGE,
        "voice_minutes_per_day": RECOMMENDED_VOICE_MINUTES_PER_DAY,
        "voice_minutes_per_week": RECOMMENDED_VOICE_MINUTES_PER_WEEK,
        "voice_minutes_per_month": RECOMMENDED_VOICE_MINUTES_PER_MONTH,
        "context_lines_per_day": RECOMMENDED_CONTEXT_LINES_PER_DAY,
        "context_lines_per_week": RECOMMENDED_CONTEXT_LINES_PER_WEEK,
        "enforce_image_day": True,
        "enforce_image_week": True,
        "enforce_image_month": True,
        "enforce_context_day": True,
        "enforce_context_week": True,
        "note": "Per-customer caps across connected channels. Not Meta-approved quotas.",
    }


def _clamp_int(value: Any, *, default: int, lo: int = 0, hi: int = _HARD_MAX_LINES) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize_ai_limit_settings(raw: dict[str, Any] | None) -> AiLimitSettings:
    data = raw if isinstance(raw, dict) else {}
    return AiLimitSettings(
        unlimited=bool(data.get("unlimited", False)),
        image_per_day=_clamp_int(data.get("image_per_day"), default=RECOMMENDED_IMAGE_PER_DAY, hi=_HARD_MAX_IMAGES),
        image_per_week=_clamp_int(data.get("image_per_week"), default=RECOMMENDED_IMAGE_PER_WEEK, hi=_HARD_MAX_IMAGES),
        image_per_month=_clamp_int(data.get("image_per_month"), default=RECOMMENDED_IMAGE_PER_MONTH, hi=_HARD_MAX_IMAGES),
        photos_per_message=_clamp_int(
            data.get("photos_per_message"), default=RECOMMENDED_PHOTOS_PER_MESSAGE, hi=_HARD_MAX_PHOTOS_MSG
        ),
        text_words_per_message=_clamp_int(
            data.get("text_words_per_message"), default=RECOMMENDED_TEXT_WORDS_PER_MESSAGE, hi=_HARD_MAX_WORDS
        ),
        text_replies_per_day=_clamp_int(
            data.get("text_replies_per_day"), default=RECOMMENDED_TEXT_REPLIES_PER_DAY, hi=_HARD_MAX_REPLIES
        ),
        text_replies_per_week=_clamp_int(
            data.get("text_replies_per_week"), default=RECOMMENDED_TEXT_REPLIES_PER_WEEK, hi=_HARD_MAX_REPLIES
        ),
        text_replies_per_month=_clamp_int(
            data.get("text_replies_per_month"), default=RECOMMENDED_TEXT_REPLIES_PER_MONTH, hi=_HARD_MAX_REPLIES
        ),
        voice_minutes_per_message=_clamp_int(
            data.get("voice_minutes_per_message"),
            default=RECOMMENDED_VOICE_MINUTES_PER_MESSAGE,
            hi=_HARD_MAX_MINUTES,
        ),
        voice_minutes_per_day=_clamp_int(
            data.get("voice_minutes_per_day"), default=RECOMMENDED_VOICE_MINUTES_PER_DAY, hi=_HARD_MAX_MINUTES
        ),
        voice_minutes_per_week=_clamp_int(
            data.get("voice_minutes_per_week"), default=RECOMMENDED_VOICE_MINUTES_PER_WEEK, hi=_HARD_MAX_MINUTES
        ),
        voice_minutes_per_month=_clamp_int(
            data.get("voice_minutes_per_month"), default=RECOMMENDED_VOICE_MINUTES_PER_MONTH, hi=_HARD_MAX_MINUTES
        ),
        context_lines_per_day=_clamp_int(
            data.get("context_lines_per_day"), default=RECOMMENDED_CONTEXT_LINES_PER_DAY, hi=_HARD_MAX_LINES
        ),
        context_lines_per_week=_clamp_int(
            data.get("context_lines_per_week"), default=RECOMMENDED_CONTEXT_LINES_PER_WEEK, hi=_HARD_MAX_LINES
        ),
        enforce_image_day=bool(data.get("enforce_image_day", True)),
        enforce_image_week=bool(data.get("enforce_image_week", True)),
        enforce_image_month=bool(data.get("enforce_image_month", True)),
        enforce_context_day=bool(data.get("enforce_context_day", True)),
        enforce_context_week=bool(data.get("enforce_context_week", True)),
        enforce_replies_day=bool(data.get("enforce_replies_day", True)),
        enforce_replies_week=bool(data.get("enforce_replies_week", True)),
        enforce_replies_month=bool(data.get("enforce_replies_month", True)),
        enforce_voice_day=bool(data.get("enforce_voice_day", True)),
        enforce_voice_week=bool(data.get("enforce_voice_week", True)),
        enforce_voice_month=bool(data.get("enforce_voice_month", True)),
    )


def count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(str(text).split())


def truncate_text_to_words(text: str, max_words: int) -> str:
    if max_words <= 0:
        return ""
    words = str(text).split()
    if len(words) <= max_words:
        return str(text)
    return " ".join(words[:max_words])


def count_non_empty_lines(text: str | None) -> int:
    if not text:
        return 0
    return sum(1 for line in str(text).splitlines() if line.strip())


def minutes_from_seconds(duration_seconds: float) -> int:
    if duration_seconds <= 0:
        return 0
    return max(1, int(math.ceil(duration_seconds / 60.0)))


def utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def day_period_key(now: datetime | None = None) -> str:
    dt = utc_now(now)
    return f"day:{dt.date().isoformat()}"


def week_period_key(now: datetime | None = None) -> str:
    dt = utc_now(now)
    iso = dt.isocalendar()
    return f"week:{iso.year}-W{iso.week:02d}"


def month_period_key(now: datetime | None = None) -> str:
    dt = utc_now(now)
    return f"month:{dt.year:04d}-{dt.month:02d}"


def period_reset_at(period: str, now: datetime | None = None) -> datetime:
    dt = utc_now(now)
    start = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
    if period == "day":
        return start + timedelta(days=1)
    if period == "week":
        days_until_monday = (7 - dt.weekday()) % 7 or 7
        return start + timedelta(days=days_until_monday)
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=UTC)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)


@dataclass
class QuotaDecision:
    allowed: bool
    reason: str | None = None
    remaining: int | None = None
    limit: int | None = None
    used: int | None = None
    period: str | None = None
    customer_message: str | None = None
    allowed_amount: int = 0
    reset_at: str | None = None
    truncated: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining": self.remaining,
            "limit": self.limit,
            "used": self.used,
            "period": self.period,
            "customer_message": self.customer_message,
            "allowed_amount": self.allowed_amount,
            "reset_at": self.reset_at,
            "truncated": self.truncated,
        }
