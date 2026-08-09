"""SSE helpers for Owner Copilot V2 streaming protocol."""

from __future__ import annotations

import json
from typing import Any

from services.owner_copilot_v2.models import StreamEvent


def encode_sse(event: StreamEvent | dict[str, Any]) -> str:
    if isinstance(event, StreamEvent):
        payload = event.to_dict()
    else:
        payload = event
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def encode_sse_done() -> str:
    return "data: {\"type\":\"stream_end\"}\n\n"
