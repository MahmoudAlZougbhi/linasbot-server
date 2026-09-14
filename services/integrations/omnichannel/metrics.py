"""In-process counters exported for Prometheus/dashboard scrapes."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = {}
_gauges: dict[str, float] = {}
_oldest: dict[str, float] = {}


def _bump(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] = int(_counters.get(name) or 0) + amount


def incr(name: str, amount: int = 1) -> None:
    _bump(name, int(amount))


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[f"omni_{name}"] = float(value)


def inbound_accepted(*, channel: str, surface: str) -> None:
    _bump("omni_inbound_accepted_total")
    _bump(f"omni_inbound_accepted_{channel}_{surface}_total")


def inbound_dead_letter(*, channel: str) -> None:
    _bump("omni_inbound_dead_letter_total")
    _bump(f"omni_inbound_dead_letter_{channel}_total")


def outbound_retry(*, provider: str) -> None:
    _bump("omni_outbound_retry_total")
    _bump(f"omni_outbound_retry_{provider}_total")


def outbound_429(*, provider: str) -> None:
    _bump("omni_provider_429_total")
    _bump(f"omni_provider_429_{provider}_total")


def set_queue_oldest(*, logical_queue: str, age_seconds: float) -> None:
    with _lock:
        _oldest[logical_queue] = float(age_seconds)
        _gauges[f"omni_queue_oldest_age_seconds_{logical_queue}"] = float(age_seconds)


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "oldest_age_seconds": dict(_oldest),
            "observed_at": time.time(),
        }
