"""Guest chat hard limits (questions + input size). No tenant mutation."""

from __future__ import annotations

import re

GUEST_MAX_QUESTIONS = 10
# Abuse guard only — not shown in guest UI.
GUEST_MAX_WORDS = 2000
# Product rule: guests cannot send oversized prompts without a subscription.
GUEST_MAX_INPUT_TOKENS = 500

_WORD_RE = re.compile(r"\S+", re.UNICODE)
# Rough parity with owner memory packing (~4 chars/token).
_CHARS_PER_TOKEN = 4

# Reject media/attachment attempts on the text-only guest endpoint.
GUEST_FORBIDDEN_MEDIA_KEYS = frozenset(
    {
        "attachment_ids",
        "attachments",
        "image",
        "images",
        "media",
        "photo",
        "photos",
        "file",
        "files",
        "video",
        "videos",
        "audio",
    }
)


def count_words(text: str) -> int:
    return len(_WORD_RE.findall((text or "").strip()))


def words_ok(text: str, *, max_words: int = GUEST_MAX_WORDS) -> bool:
    return count_words(text) <= max_words


def estimate_guest_tokens(text: str) -> int:
    """Estimate input tokens for guest size gate (~4 chars/token)."""
    stripped = (text or "").strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // _CHARS_PER_TOKEN)


def tokens_ok(text: str, *, max_tokens: int = GUEST_MAX_INPUT_TOKENS) -> bool:
    return estimate_guest_tokens(text) <= max_tokens


def remaining_questions(used: int, *, max_questions: int = GUEST_MAX_QUESTIONS) -> int:
    return max(0, max_questions - max(0, int(used)))


def payload_has_guest_media(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in payload:
        if str(key).strip().lower() in GUEST_FORBIDDEN_MEDIA_KEYS:
            return True
    return False
