"""
Wraps any WhatsApp adapter so identical outbound text to the same recipient is not
delivered twice within the outbound dedupe window (applies to all providers).
"""

from __future__ import annotations

from typing import Any, Dict

from .base_adapter import WhatsAppAdapter
from .outbound_text_dedupe import finish_outbound_text_attempt, should_skip_outbound_text


class DedupeOutboundTextAdapter:
    """Process-wide text dedupe in front of Meta, Qiscus, MontyMobile, 360dialog, etc."""

    def __init__(self, inner: WhatsAppAdapter):
        self._inner = inner
        self.client = getattr(inner, "client", None)
        self.provider_name = getattr(inner, "provider_name", "unknown")

    def _resolve_recipient(self, to_number: str) -> str:
        inner: Any = self._inner
        while hasattr(inner, "_real"):
            inner = inner._real
        if hasattr(inner, "_get_phone_from_room_id"):
            return inner._get_phone_from_room_id(to_number)
        return to_number

    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        resolved = self._resolve_recipient(to_number)
        if await should_skip_outbound_text(resolved, message):
            return {"success": True, "deduped_outbound": True}
        send_success = False
        try:
            result = await self._inner.send_text_message(to_number, message)
            send_success = bool(result and result.get("success"))
            return result
        finally:
            await finish_outbound_text_attempt(resolved, message, send_success)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
