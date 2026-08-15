"""Compatibility shim — canonical catalog lives in iso639_languages."""

from __future__ import annotations

from services.cm.iso639_languages import (
    iso639_catalog,
    iso639_label,
    iso639_native_label,
    is_valid_iso639_code,
    normalize_language_code,
)

SMART_ANSWER_LANGUAGE_CATALOG = tuple(iso639_catalog())

__all__ = [
    "SMART_ANSWER_LANGUAGE_CATALOG",
    "iso639_catalog",
    "iso639_label",
    "iso639_native_label",
    "is_valid_iso639_code",
    "is_valid_smart_answer_language",
    "normalize_language_code",
]


def is_valid_smart_answer_language(code: str | None) -> bool:
    return bool(normalize_language_code(code))
