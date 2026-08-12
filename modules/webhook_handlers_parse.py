"""Webhook payload parse helpers (LOC split)."""

from __future__ import annotations

from typing import Any

from modules.models import WebhookRequest
from modules.webhook_handlers_dedupe import _synthetic_inbound_id_from_wa_message


def _webhook_is_meta_status_only(webhook_data: dict[str, Any]) -> bool:
    """WhatsApp Cloud API sends delivery/read/sent updates with statuses[] and no messages[]."""
    try:
        entries = webhook_data.get("entry") or []
        if not entries or not isinstance(entries, list):
            return False
        entry = entries[0] if isinstance(entries[0], dict) else {}
        changes = entry.get("changes") or []
        if not changes or not isinstance(changes, list):
            return False
        ch = changes[0] if isinstance(changes[0], dict) else {}
        value = ch.get("value") or {}
        if not isinstance(value, dict):
            return False
        msgs = value.get("messages") or []
        return bool(value.get("statuses")) and not msgs
    except Exception:
        return False


def _parse_webhook_raw_dict(webhook_data: dict[str, Any]) -> dict[str, Any] | None:
    """Last-resort: extract from entry/changes/value/messages using raw dict (no Pydantic)."""
    try:
        entries = webhook_data.get("entry") or []
        if not entries or not isinstance(entries, list):
            return None
        entry = entries[0] if isinstance(entries[0], dict) else {}
        changes = entry.get("changes") or []
        if not changes or not isinstance(changes, list):
            return None
        ch = changes[0] if isinstance(changes[0], dict) else {}
        value = ch.get("value") or {}
        if not isinstance(value, dict):
            return None
        if "statuses" in value:
            return None
        messages = value.get("messages") or []
        if not messages or not isinstance(messages, list):
            return None
        msg = messages[0] if isinstance(messages[0], dict) else {}
        _mid = (msg.get("id") or "").strip()
        if not _mid:
            _mid = _synthetic_inbound_id_from_wa_message(msg)
        msg_from = str(msg.get("from") or "").strip()
        if not msg_from:
            contacts = value.get("contacts") or []
            if contacts and isinstance(contacts[0], dict):
                msg_from = str(contacts[0].get("wa_id") or "").strip()
        if not msg_from:
            return None
        phone = f"+{msg_from}" if msg_from and not msg_from.startswith("+") else msg_from
        msg_type = msg.get("type") or "text"
        text_body = (msg.get("text") or {}) if isinstance(msg.get("text"), dict) else {}
        text = str(text_body.get("body") or "")
        content: dict[str, Any]
        if msg_type == "text":
            content = {"text": text}
        elif msg_type == "audio":
            audio_obj = msg.get("audio") or {}
            audio_id = (
                audio_obj.get("id") or audio_obj.get("link") or audio_obj.get("url") or ""
                if isinstance(audio_obj, dict)
                else ""
            )
            content = {"audio_id": audio_id}
        elif msg_type == "image":
            img_obj = msg.get("image") or {}
            img_id = img_obj.get("id") or "" if isinstance(img_obj, dict) else ""
            content = {"image_id": img_id}
        else:
            content = {"raw": msg}
        return {
            "user_id": phone,
            "user_name": phone,
            "message_id": f"raw_{_mid}",
            "timestamp": msg.get("timestamp", ""),
            "type": msg_type,
            "content": content,
            "phone_number": phone,
        }
    except Exception as e:
        print(f"Raw webhook parse failed: {e}")
        return None


async def handle_meta_webhook(webhook_data: dict[str, Any]) -> dict[str, Any] | None:
    """Handle Meta/WhatsApp Cloud API webhook format (fallback)"""
    try:
        request_body = WebhookRequest(**webhook_data)

        for entry in request_body.entry:
            for change in entry.changes:
                if change.field == "messages" and change.value.messages:
                    for message in change.value.messages:
                        user_whatsapp_id = message.from_
                        user_name = next(
                            (c.profile.name for c in (change.value.contacts or []) if c.wa_id == user_whatsapp_id),
                            user_whatsapp_id,
                        )

                        return {
                            "user_id": user_whatsapp_id,
                            "user_name": user_name,
                            "message_id": message.id,
                            "timestamp": message.timestamp,
                            "type": message.type,
                            "content": extract_meta_message_content(message),
                        }
        return None
    except Exception as e:
        print(f"Error parsing Meta webhook: {e}")
        return None


def extract_meta_message_content(message: Any) -> dict[str, Any]:
    """Extract content from Meta message format"""
    if message.type == "text":
        return {"text": message.text.body}
    elif message.type == "image":
        return {"image_id": message.image.id, "caption": getattr(message.image, "caption", None)}
    elif message.type == "audio":
        return {"audio_id": message.audio.id}
    elif message.type == "video":
        return {"video_id": message.video.id, "caption": getattr(message.video, "caption", None)}
    elif message.type == "document":
        return {"document_id": message.document.id, "filename": getattr(message.document, "filename", None)}
    else:
        return {"raw": message.model_dump()}


def _count_non_empty_lines(text: str) -> int:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return len([line for line in normalized.split("\n") if line.strip()])


def _is_image_attachment(item: Any) -> bool:
    if isinstance(item, str):
        lower = item.lower()
        return lower.startswith("data:image/") or any(
            ext in lower for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif")
        )

    if isinstance(item, dict):
        item_type = str(item.get("type") or item.get("mime_type") or "").lower()
        if "image" in item_type:
            return True
        candidate = item.get("url") or item.get("image_id") or item.get("image_url") or item.get("link") or ""
        return _is_image_attachment(candidate)

    return False


def _count_images_in_single_message(message_type: str, content: Any) -> int:
    if isinstance(content, dict):
        for key in ("images", "image_ids", "image_urls"):
            values = content.get(key)
            if isinstance(values, list):
                return sum(1 for item in values if _is_image_attachment(item) or item)

        attachments = content.get("attachments")
        if isinstance(attachments, list):
            return sum(1 for item in attachments if _is_image_attachment(item))

        if content.get("image_id") or content.get("image_url"):
            return 1

    if isinstance(content, list):
        return sum(1 for item in content if _is_image_attachment(item) or item)

    if message_type == "image":
        return 1

    return 0

