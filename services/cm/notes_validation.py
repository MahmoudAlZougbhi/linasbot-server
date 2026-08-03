"""Deterministic Notes validators (plan §7). Structured fields always win."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Currency / price override claims in free-text Notes.
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?:"
    r"(?:\$|€|£)\s*\d+(?:[.,]\d{1,3})?"
    r"|\d+(?:[.,]\d{1,3})?\s*(?:\$|€|£|usd|eur|lbp|ll|ل\.?ل\.?|دولار|يورو)"
    r"|(?:price|prix|سعر|كلفة|تكلفة)\s*(?:is|est|:|=|هو)?\s*\d+"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# E.164-style public contact numbers (Notes must not introduce handoff phones).
_E164_RE = re.compile(r"(?<!\w)\+\d{8,15}(?!\w)")

# Availability / offer toggles that conflict with structured availability.
_AVAILABILITY_CLAIM_RE = re.compile(
    r"(?:"
    r"\b(?:not\s+)?(?:available|unavailable)\b"
    r"|\bwe\s+(?:do\s+not|don't|dont)\s+offer\b"
    r"|\bwe\s+offer\b"
    r"|\b(?:currently\s+)?(?:offered|not\s+offered)\b"
    r"|متوفر|غير\s*متوفر|ما\s*منقدم|ما\s*نقدّم|نقدم|نقدّم|"
    r"disponible|indisponible|nous\s+proposons|nous\s+ne\s+proposons\s+pas"
    r")",
    re.IGNORECASE | re.UNICODE,
)

NOTES_CURRENCY_AMOUNT = "NOTES_CURRENCY_AMOUNT"
NOTES_E164_PHONE = "NOTES_E164_PHONE"
NOTES_AVAILABILITY_OVERRIDE = "NOTES_AVAILABILITY_OVERRIDE"


def validate_notes(notes: str | None, *, path: str = "notes") -> list[str]:
    """Return deterministic error codes for untrusted Notes text.

    Empty/None Notes are valid. Notes must not claim prices, E.164 phones,
    or availability toggles that could override structured fields.
    """
    text = (notes or "").strip()
    if not text:
        return []

    codes: list[str] = []
    if _CURRENCY_AMOUNT_RE.search(text):
        codes.append(NOTES_CURRENCY_AMOUNT)
    if _E164_RE.search(text):
        codes.append(NOTES_E164_PHONE)
    if _AVAILABILITY_CLAIM_RE.search(text):
        codes.append(NOTES_AVAILABILITY_OVERRIDE)
    # ``path`` reserved for API mapping; codes stay stable for clients/tests.
    _ = path
    return codes


def validate_notes_in_payload(payload: dict[str, object], *, path_prefix: str = "") -> list[str]:
    """Walk a section payload and validate every ``notes`` string field."""
    codes: list[str] = []
    for note_path, note_text in _iter_notes(payload, path_prefix or "payload"):
        for code in validate_notes(note_text, path=note_path):
            if code not in codes:
                codes.append(code)
    return codes


def _iter_notes(
    value: object,
    path: str,
) -> Iterable[tuple[str, str | None]]:
    if isinstance(value, dict):
        notes = value.get("notes")
        if isinstance(notes, str) or notes is None:
            if "notes" in value:
                yield path + ".notes", notes if isinstance(notes, str) else None
        for key, child in value.items():
            if key == "notes":
                continue
            child_path = f"{path}.{key}" if path else str(key)
            yield from _iter_notes(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_notes(child, f"{path}[{index}]")
