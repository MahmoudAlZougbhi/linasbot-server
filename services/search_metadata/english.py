"""English-only checks for internal Luna search metadata."""

from __future__ import annotations

import re

# Block non-Latin scripts. French/German stay Latin; the prompt requires English.
_NON_ENGLISH_SCRIPT = re.compile(
    r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF"
    r"\u0900-\u097F\u0E00-\u0E7F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]"
)


def contains_non_english_script(text: str) -> bool:
    return bool(_NON_ENGLISH_SCRIPT.search(text or ""))


def english_only_or_empty(text: str) -> str:
    """Keep compact English text; drop anything containing a non-English script."""
    value = " ".join(str(text or "").split())
    if not value or contains_non_english_script(value):
        return ""
    return value
