"""Lightweight in-process counters for scale observability (export via /api/scale/metrics)."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.RLock()
_counters: dict[str, float] = {}
_started = time.time()


def incr(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] = float(_counters.get(name, 0.0)) + value


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _counters[name] = float(value)


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "uptime_seconds": max(0.0, time.time() - _started),
            "counters": dict(_counters),
        }
