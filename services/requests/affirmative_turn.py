"""Whole-message check for a pending-request confirmation.

This does not run unless LINAS_FLAG_REQUEST_CONFIRM is on, and it does not
classify ordinary chat. The customer's words still reach Terra on every other turn.
"""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\u0600-\u06FF]+", re.UNICODE)

_AFFIRMATIVE = frozenset(
    {
        "yes",
        "yes confirm",
        "yes confirm send it",
        "confirm",
        "oui",
        "تمام",
        "eh akid",
        "eh akked",
    }
)


def turn_is_affirmative(message: str) -> bool:
    text = _PUNCT.sub(" ", (message or "").casefold())
    text = _SPACE.sub(" ", text).strip()
    return text in _AFFIRMATIVE
