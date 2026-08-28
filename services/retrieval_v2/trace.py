"""Structured observability events for Retrieval V2 (no raw business text by default)."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def new_operation_id() -> str:
    return uuid.uuid4().hex


@dataclass
class RetrievalV2Trace:
    operation_id: str
    tenant_id: str
    operation: str
    provider: str = ""
    model: str = ""
    dimensions: int = 0
    source_type: str = ""
    source_id: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    status: str = "ok"
    error_code: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Never dump free-form customer/business text into default traces.
        return payload


class TraceTimer:
    def __init__(self) -> None:
        self._started = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self._started) * 1000.0, 3)
