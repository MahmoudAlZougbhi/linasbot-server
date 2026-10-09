"""Append a request notice onto a web chat session. No live send until the flag is on."""

from __future__ import annotations

_NOTICES: list[dict[str, str]] = []


def reset_notices_for_tests() -> None:
    _NOTICES.clear()


def record_notice(*, tenant_id: str, conversation_id: str | None, text: str) -> None:
    _NOTICES.append(
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id or "",
            "text": text,
            "role": "assistant",
        }
    )


def notices() -> list[dict[str, str]]:
    return list(_NOTICES)
