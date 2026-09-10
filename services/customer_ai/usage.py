"""Internal provider usage ledger. No new customer SKU."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageEvent:
    provider: str
    operation: str
    model: str
    tokens: int = 0
    calls: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


def usage_dict(events: list[UsageEvent]) -> dict[str, Any]:
    return {
        "events": [
            {
                "provider": item.provider,
                "operation": item.operation,
                "model": item.model,
                "tokens": item.tokens,
                "calls": item.calls,
            }
            for item in events
        ],
        "providers": sorted({item.provider for item in events}),
    }
