"""Widget poll delay grows from 5 seconds to 30 seconds."""

from __future__ import annotations


def poll_delay_seconds(attempt: int) -> int:
    step = max(0, int(attempt))
    return min(30, 5 * (2**step) if step else 5)
