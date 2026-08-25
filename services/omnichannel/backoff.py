"""Provider-aware retry delay: honor Retry-After, else jittered exponential cap."""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

from services.omnichannel.headers import parse_retry_after_seconds

DEFAULT_CAP_SECONDS = 300.0
DEFAULT_BASE_SECONDS = 1.0


def exponential_backoff_seconds(
    attempt: int,
    *,
    base: float = DEFAULT_BASE_SECONDS,
    cap: float = DEFAULT_CAP_SECONDS,
) -> float:
    safe_attempt = max(0, min(int(attempt), 12))
    exp = min(cap, base * (2**safe_attempt))
    jitter = random.random() * min(1.0, exp * 0.25)
    return float(min(cap, exp + jitter))


def delay_for_provider(
    *,
    attempt: int,
    headers: Mapping[str, Any] | None = None,
    fallback_seconds: float | None = None,
    cap: float = DEFAULT_CAP_SECONDS,
) -> float:
    requested = parse_retry_after_seconds(headers)
    if requested is not None:
        return min(cap, max(0.05, requested))
    if fallback_seconds is not None:
        return min(cap, max(0.05, float(fallback_seconds)))
    return exponential_backoff_seconds(attempt, cap=cap)
