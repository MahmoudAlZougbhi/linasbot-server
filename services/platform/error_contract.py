"""Stable error bodies in English, Arabic, and French."""

from __future__ import annotations

from typing import Any


def error_body(
    code: str, message: str, message_ar: str, message_fr: str, *, retry_after: int | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "success": False,
        "error": code,
        "message": message,
        "message_ar": message_ar,
        "message_fr": message_fr,
    }
    if retry_after is not None:
        body["retry_after"] = retry_after
    return body
