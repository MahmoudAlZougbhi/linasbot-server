"""Meta public comments stay on the durable inbound processor; do not double-send."""

from __future__ import annotations

from typing import Any


async def deliver_meta_comment(_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "http_status": 409,
        "error": "meta_comment_uses_inbound_processor",
        "submitted": False,
    }
