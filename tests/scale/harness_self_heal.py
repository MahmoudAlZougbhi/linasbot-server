"""Restart backoff so a crashing worker cannot spin the supervisor."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RestartDecision:
    allowed: bool
    delay_seconds: float
    reason: str


def decide_restart(
    *,
    restart_count: int,
    recent_starts: list[float],
    now: float | None = None,
    window_seconds: float = 60.0,
    max_in_window: int = 5,
    base_delay: float = 0.2,
    max_delay: float = 30.0,
) -> RestartDecision:
    """Exponential backoff + jitter. Refuse when the crash loop is too fast."""
    ts = time.time() if now is None else float(now)
    recent = [float(item) for item in recent_starts if ts - float(item) <= window_seconds]
    if len(recent) >= max_in_window:
        return RestartDecision(
            allowed=False,
            delay_seconds=max_delay,
            reason="restart_rate_limited",
        )
    exponent = max(0, int(restart_count))
    delay = min(max_delay, base_delay * (2 ** min(exponent, 8)))
    jitter = random.uniform(0.0, delay * 0.25)
    return RestartDecision(
        allowed=True,
        delay_seconds=round(delay + jitter, 3),
        reason="backoff",
    )
