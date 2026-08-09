"""Guest chat hard limits (questions + words). No tenant mutation."""

from __future__ import annotations

import re

GUEST_MAX_QUESTIONS = 10
GUEST_MAX_WORDS = 50

_WORD_RE = re.compile(r"\S+", re.UNICODE)


def count_words(text: str) -> int:
    return len(_WORD_RE.findall((text or "").strip()))


def words_ok(text: str, *, max_words: int = GUEST_MAX_WORDS) -> bool:
    return count_words(text) <= max_words


def remaining_questions(used: int, *, max_questions: int = GUEST_MAX_QUESTIONS) -> int:
    return max(0, max_questions - max(0, int(used)))
