"""Upload stored media bytes to Meta and send as a Messenger attachment.

Uses Graph message_attachments (multipart) so files never need a public URL.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


def attachment_type_for_mime(mime: str) -> str:
    mime_l = str(mime or "").lower()
    if mime_l.startswith("video/"):
        return "video"
    if mime_l.startswith("audio/"):
        return "audio"
    if mime_l.startswith("image/"):
        return "image"
    return "file"


async def send_stored_meta_attachment(
    adapter: Any,
    *,
    recipient_id: str,
    media_bytes: bytes,
    mime: str,
    filename: str,
    product_id: str = "",
    recipient_field: str = "id",
) -> dict[str, Any]:
    to_id = str(recipient_id or "").strip()
    if not to_id or not media_bytes:
        return {"success": False, "error": "missing_recipient_or_bytes"}
    mime_l = str(mime or "image/jpeg").lower()
    att_type = attachment_type_for_mime(mime_l)
    base = str(getattr(adapter, "graph_base_url", "") or "https://graph.facebook.com").rstrip("/")
    version = str(getattr(adapter, "graph_api_version", "") or "v24.0")
    account_id = str(getattr(adapter, "account_id", "") or "").strip()
    token = str(getattr(adapter, "access_token", "") or "").strip()
    client: httpx.AsyncClient | None = getattr(adapter, "client", None)
    if not account_id or not token or client is None:
        return {"success": False, "error": "adapter_not_ready"}
    upload_url = f"{base}/{version}/{account_id}/message_attachments"
    files = {"filedata": (filename or "media.bin", media_bytes, mime_l)}
    data = {"message": json.dumps({"attachment": {"type": att_type, "payload": {"is_reusable": True}}})}
    try:
        uploaded = await client.post(
            upload_url,
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {token}"},
        )
        body = uploaded.json() if uploaded.content else {}
    except (httpx.HTTPError, ValueError):
        return {"success": False, "error": "attachment_upload_failed"}
    if not isinstance(body, dict) or body.get("error") or uploaded.status_code >= 300:
        return {"success": False, "error": f"attachment_upload_http_{uploaded.status_code}"}
    attachment_id = str(body.get("attachment_id") or body.get("id") or "").strip()
    if not attachment_id:
        return {"success": False, "error": "missing_attachment_id"}
    field = "comment_id" if recipient_field == "comment_id" else "id"
    payload = {
        "recipient": {field: to_id},
        "messaging_type": "RESPONSE",
        "message": {"attachment": {"type": att_type, "payload": {"attachment_id": attachment_id}}},
    }
    try:
        sent = await adapter._post(payload)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)[:180]}
    message_id = str(sent.get("message_id") or sent.get("id") or "").strip()
    if not message_id:
        return {"success": False, "provider": "meta", "error": "meta_send_missing_message_id"}
    _ = product_id
    return {"success": True, "provider": "meta", "message_id": message_id, "attachment_id": attachment_id}


async def send_stored_product_media(
    adapter: Any,
    *,
    recipient_id: str,
    media_bytes: bytes,
    mime: str,
    filename: str,
    product_id: str = "",
) -> dict[str, Any]:
    return await send_stored_meta_attachment(
        adapter,
        recipient_id=recipient_id,
        media_bytes=media_bytes,
        mime=mime,
        filename=filename,
        product_id=product_id,
    )
