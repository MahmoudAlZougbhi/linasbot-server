"""Durable Copilot turn events and a hard lab deadline."""

from __future__ import annotations

import asyncio
from typing import Any

_EVENTS: dict[str, list[dict[str, Any]]] = {}
_SETTLED: set[str] = set()


def reset_turns_for_tests() -> None:
    _EVENTS.clear()
    _SETTLED.clear()


def append_event(turn_id: str, event: dict[str, Any]) -> None:
    _EVENTS.setdefault(turn_id, []).append(dict(event))


def replay(turn_id: str) -> list[dict[str, Any]]:
    return list(_EVENTS.get(turn_id) or [])


def settle_once(turn_id: str) -> bool:
    if turn_id in _SETTLED:
        return False
    _SETTLED.add(turn_id)
    return True


async def run_with_deadline(work: Any, *, seconds: float = 60) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(work, timeout=seconds)
    except TimeoutError:
        return {"ok": False, "error": "timed_out", "message": "This took too long. Try a smaller question."}
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": result}
