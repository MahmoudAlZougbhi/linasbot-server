"""
Safe Send Adapter – local/dry-run wrapper for outbound WhatsApp.
When APP_MODE=local or ENV=development, or ENABLE_SENDING=false:
- Option 1 (sandbox): only numbers in LOCAL_ALLOWED_WHATSAPP_NUMBERS receive real messages.
- Option 2 (dry-run): when ENABLE_SENDING=false, no real sends; all go to log as "would send".
Recipients not allowed get dry-run: log to data/dry_run_messages.jsonl and return {success: True, dry_run: True}.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import config
from .base_adapter import WhatsAppAdapter
from storage.persistent_storage import DRY_RUN_MESSAGES_FILE, ensure_dirs

_DRY_RUN_LOG = DRY_RUN_MESSAGES_FILE


def _should_dry_run(to_number: str) -> bool:
    """True if we must not send for real (dry-run or not in sandbox list)."""
    if not config.ENABLE_SENDING:
        return True
    if not config.is_local_env():
        return False
    # Local mode with sending enabled: only allow sandbox numbers
    normalized = to_number.strip().replace(" ", "").replace("-", "")
    allowed_normalized = {n.replace(" ", "").replace("-", "") for n in config.LOCAL_ALLOWED_WHATSAPP_NUMBERS}
    return normalized not in allowed_normalized


def _log_dry_run(to_number: str, message_type: str, payload: Dict[str, Any]) -> None:
    """Append one dry-run entry to persistent dry_run_messages.jsonl."""
    ensure_dirs()
    entry = {
        "at": datetime.utcnow().isoformat() + "Z",
        "to": to_number,
        "type": message_type,
        "payload": payload,
    }
    try:
        with open(str(_DRY_RUN_LOG), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ Could not write dry-run log: {e}")
    print(f"📋 [DRY-RUN] Would send {message_type} to {to_number[:8]}*** (see {_DRY_RUN_LOG})")


class SafeSendAdapter(WhatsAppAdapter):
    """Wraps a real WhatsApp adapter and enforces local/dry-run rules."""

    def __init__(self, real_adapter: WhatsAppAdapter):
        self._real = real_adapter
        self.client = getattr(real_adapter, "client", None)
        self.provider_name = getattr(real_adapter, "provider_name", "unknown")

    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        if _should_dry_run(to_number):
            _log_dry_run(to_number, "text", {"message": message[:500]})
            return {"success": True, "dry_run": True}
        return await self._real.send_text_message(to_number, message)

    async def send_image_message(
        self, to_number: str, image_url: str, caption: str = None
    ) -> Dict[str, Any]:
        if _should_dry_run(to_number):
            _log_dry_run(to_number, "image", {"image_url": image_url[:200], "caption": (caption or "")[:200]})
            return {"success": True, "dry_run": True}
        return await self._real.send_image_message(to_number, image_url, caption)

    async def download_media(self, media_id: str) -> bytes:
        return await self._real.download_media(media_id)

    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        return await self._real.set_webhook(webhook_url)

    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._real.parse_webhook_message(webhook_data)

    async def close(self):
        if hasattr(self._real, "close") and callable(self._real.close):
            await self._real.close()

    # Optional methods (MontyMobile, etc.)
    async def send_audio_message(
        self, to_number: str, audio_url: str, audio_base64: str = None
    ) -> Dict[str, Any]:
        if _should_dry_run(to_number):
            _log_dry_run(to_number, "audio", {"audio_url": audio_url[:200] if audio_url else "base64"})
            return {"success": True, "dry_run": True}
        if hasattr(self._real, "send_audio_message"):
            return await self._real.send_audio_message(to_number, audio_url, audio_base64)
        return {"success": False, "error": "Adapter does not support send_audio_message"}

    async def send_template_message(
        self,
        to_number: str,
        template_name: str,
        language_code: str = "en",
        parameters: list = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if _should_dry_run(to_number):
            _log_dry_run(
                to_number,
                "template",
                {"template_name": template_name, "language_code": language_code, "parameters": parameters or []},
            )
            return {"success": True, "dry_run": True}
        if hasattr(self._real, "send_template_message"):
            return await self._real.send_template_message(
                to_number, template_name, language_code, parameters, **kwargs
            )
        return {"success": False, "error": "Adapter does not support send_template_message"}
