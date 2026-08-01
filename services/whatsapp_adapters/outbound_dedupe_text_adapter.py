"""
Wraps any WhatsApp adapter so identical outbound text to the same recipient is not
delivered twice within the outbound dedupe window (applies to all providers).
"""

from __future__ import annotations

from typing import Any

from services.outbound_text_firestore_dedupe import (
    release_outbound_send_firestore,
    try_acquire_outbound_send_firestore,
)
from utils.phone_utils import phone_match_key

from .base_adapter import WhatsAppAdapter
from .outbound_text_dedupe import (
    finish_outbound_text_attempt,
    normalize_text_body_for_dedupe,
    should_skip_outbound_text,
)


class DedupeOutboundTextAdapter(WhatsAppAdapter):
    """Process-wide text dedupe in front of Meta, Qiscus, MontyMobile, 360dialog, etc."""

    def __init__(self, inner: WhatsAppAdapter) -> None:
        super().__init__(getattr(inner, "api_token", ""), getattr(inner, "phone_number_id", None))
        self._inner = inner
        self.client: Any = getattr(inner, "client", None)
        self.provider_name = getattr(inner, "provider_name", "unknown")

    def _resolve_recipient(self, to_number: str) -> str:
        inner: Any = self._inner
        while hasattr(inner, "_real"):
            inner = inner._real
        if hasattr(inner, "_get_phone_from_room_id"):
            resolved = inner._get_phone_from_room_id(to_number)
        else:
            resolved = to_number
        pk = phone_match_key(resolved)
        if pk:
            return pk
        return (resolved or "").strip()

    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        resolved = self._resolve_recipient(to_number)
        if await should_skip_outbound_text(resolved, message):
            return {"success": True, "deduped_outbound": True}

        body_norm = normalize_text_body_for_dedupe(message)
        fs_doc = await try_acquire_outbound_send_firestore(resolved, body_norm)
        if fs_doc is None:
            print(
                f"⚠️ Outbound duplicate suppressed (Firestore cross-replica): "
                f"recipient={resolved[:16]}… text_len={len(message or '')}"
            )
            await finish_outbound_text_attempt(resolved, message, False)
            return {"success": True, "deduped_outbound": True}

        send_success = False
        try:
            result = await self._inner.send_text_message(to_number, message)
            send_success = bool(result and result.get("success"))
            return result
        finally:
            await finish_outbound_text_attempt(resolved, message, send_success)
            if fs_doc:
                await release_outbound_send_firestore(fs_doc, send_success)

    async def send_image_message(self, to_number: str, image_url: str, caption: str | None = None) -> dict[str, Any]:
        return await self._inner.send_image_message(to_number, image_url, caption)

    async def download_media(self, media_id: str) -> bytes:
        return await self._inner.download_media(media_id)

    async def set_webhook(self, webhook_url: str) -> dict[str, Any]:
        return await self._inner.set_webhook(webhook_url)

    def parse_webhook_message(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        return self._inner.parse_webhook_message(webhook_data)

    async def close(self) -> None:
        await self._inner.close()

    async def send_audio_message(
        self, to_number: str, audio_url: str, audio_base64: str | None = None
    ) -> dict[str, Any]:
        return await self._inner.send_audio_message(to_number, audio_url, audio_base64)
