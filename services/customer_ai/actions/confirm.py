"""Revision-bound confirmation. Model confirmed=true is not enough."""

from __future__ import annotations

import re

_YES = re.compile(
    r"^\s*(yes|yep|yeah|ok|okay|sure|confirm|confirmed|نعم|اي|أي|تمام|موافق|اوك)\s*[.!]?\s*$",
    re.I,
)


def looks_like_confirmation(text: str) -> bool:
    return bool(_YES.match((text or "").strip()))


def confirmation_valid(
    *,
    message_id: str,
    customer_text: str,
    expected_revision: str,
    current_revision: str,
) -> bool:
    if not (message_id or "").strip():
        return False
    if expected_revision and expected_revision != (current_revision or ""):
        return False
    return looks_like_confirmation(customer_text)
