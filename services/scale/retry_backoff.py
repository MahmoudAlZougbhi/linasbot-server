"""Backoff for retryable infrastructure errors. Caps storms without hiding failures."""

from __future__ import annotations

_INFRA_MARKERS = (
    "operationalerror",
    "disconnectionerror",
    "timeout",
    "connection refused",
    "connection reset",
    "could not connect",
    "redis",
    "whatsappdatabaseunavailable",
    "sessionstoreunavailable",
    "psycopg",
    "server closed the connection",
)


def retry_delay_seconds(*, attempts: int, error: str, base: float | None = None) -> float:
    """Exponential delay with a floor for DB/Redis outages so workers do not spin."""
    n = max(1, int(attempts))
    delay = float(base) if base is not None else float(min(300, 2 ** min(n, 8)))
    text = (error or "").lower()
    if any(marker in text for marker in _INFRA_MARKERS):
        delay = max(delay, 5.0)
        delay = min(delay, 30.0)
    return max(0.2, delay)
