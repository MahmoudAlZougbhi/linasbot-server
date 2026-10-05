"""In-process estimate of Firestore reads and writes by code path.

These numbers are what the process believes it asked for. They are not the
Cloud Monitoring counter, which stays unavailable while billing is off.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_totals: dict[str, dict[str, int]] = {}
_last_log = 0.0


def record_usage(source: str, *, reads: int = 0, writes: int = 0) -> None:
    global _last_log
    name = (source or "unknown").strip() or "unknown"
    with _lock:
        bucket = _totals.setdefault(name, {"reads": 0, "writes": 0})
        bucket["reads"] += max(0, int(reads))
        bucket["writes"] += max(0, int(writes))
        now = time.time()
        if now - _last_log < 60:
            return
        _last_log = now
        snapshot = {key: dict(value) for key, value in _totals.items()}
    parts = [f"{key}:r={row['reads']},w={row['writes']}" for key, row in sorted(snapshot.items())]
    print("[firestore-usage] " + " ".join(parts), flush=True)


def usage_snapshot() -> dict[str, dict[str, int]]:
    with _lock:
        return {key: dict(value) for key, value in _totals.items()}
