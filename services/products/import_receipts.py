"""Remember a finished import so a retry does not create the same rows again."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

_LOCK = threading.Lock()
_RECEIPTS: dict[str, dict[str, Any]] = {}


def reset_import_receipts_for_tests() -> None:
    with _LOCK:
        _RECEIPTS.clear()


def receipt_for(tenant_id: str, body: str) -> dict[str, Any]:
    key = hashlib.sha256(f"{tenant_id}\n{body}".encode()).hexdigest()
    with _LOCK:
        found = _RECEIPTS.get(key)
        if found is None:
            found = {"key": key, "names": [], "created": 0, "done": False}
            _RECEIPTS[key] = found
        return found
