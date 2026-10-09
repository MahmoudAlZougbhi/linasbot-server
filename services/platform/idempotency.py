"""Store a create response for 24 hours so a retry does not duplicate it."""

from __future__ import annotations

import time
from typing import Any

_TTL = 24 * 60 * 60
_STORE: dict[str, tuple[float, dict[str, Any]]] = {}


def reset_idempotency() -> None:
    _STORE.clear()


def remember(key: str, response: dict[str, Any]) -> dict[str, Any]:
    _STORE[key] = (time.time() + _TTL, response)
    return response


def replay(key: str) -> dict[str, Any] | None:
    found = _STORE.get(key)
    if found is None:
        return None
    expires, response = found
    if expires < time.time():
        _STORE.pop(key, None)
        return None
    return response
