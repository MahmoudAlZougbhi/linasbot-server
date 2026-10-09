"""Remember that a customer turn produced no reply."""

from __future__ import annotations

_FAILED: dict[str, str] = {}


def reset_ai_failed_for_tests() -> None:
    _FAILED.clear()


def note_ai_failed(*, conversation_id: str, stage: str) -> None:
    if conversation_id:
        _FAILED[conversation_id] = stage or "failed"


def conversation_ai_status(conversation_id: str) -> str:
    if conversation_id in _FAILED:
        return "ai_failed"
    return ""
