"""Turn bad input into a validation error instead of a 500."""

from __future__ import annotations


class InputRejected(ValueError):
    pass


def parse_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise InputRejected(f"{name} must be a whole number")
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise InputRejected(f"{name} must be a whole number") from exc


def limit_text(value: str, *, maximum: int, name: str) -> str:
    text = value or ""
    if len(text) > maximum:
        raise InputRejected(f"{name} is too long")
    return text
