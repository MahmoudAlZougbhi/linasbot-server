"""Revision-bound confirmation. Model confirmed=true is not enough."""

from __future__ import annotations

import re

_YES = re.compile(
    r"^\s*(yes|yep|yeah|ok|okay|sure|confirm|confirmed|نعم|اي|أي|تمام|موافق|اوك)\s*[.!]?\s*$",
    re.I,
)


MATERIAL_FIELDS = (
    "service",
    "date",
    "branch",
    "price",
    "quote",
    "quantity",
    "variant",
    "recipient",
)


def looks_like_confirmation(text: str) -> bool:
    return bool(_YES.match((text or "").strip()))


def _norm(value: object) -> str:
    return str(value or "").strip().casefold()


def material_fields_changed(previous: dict | None, current: dict | None) -> bool:
    before = previous or {}
    after = current or {}
    keys = set(MATERIAL_FIELDS) | {key for key in after if key in MATERIAL_FIELDS}
    return any(_norm(before.get(key)) != _norm(after.get(key)) for key in keys)


def next_draft_revision(current: str) -> str:
    text = (current or "").strip()
    if text.isdigit():
        return str(int(text) + 1)
    if text.startswith("draft-") and text.split("-", 1)[-1].isdigit():
        return f"draft-{int(text.split('-', 1)[-1]) + 1}"
    if not text:
        return "1"
    return f"{text}+1"


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
