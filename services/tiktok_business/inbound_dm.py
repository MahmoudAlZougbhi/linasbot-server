"""Hydrate TikTok DM attachments for Customer Brain. Fail soft; no invented transcripts."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.inbound_media import inbound_from_attachment_type


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def message_text_from_content(content: dict[str, Any] | None) -> str:
    data = content if isinstance(content, dict) else {}
    raw = data.get("text")
    if raw is None:
        raw = data.get("message")
    if isinstance(raw, dict):
        return str(raw.get("body") or raw.get("text") or "").strip()
    return str(raw or "").strip()


def _kind_from_content(content: dict[str, Any]) -> str:
    raw = str(content.get("message_type") or content.get("type") or "").strip().lower()
    if raw in {"image", "photo", "img"}:
        return "image"
    if raw in {"audio", "voice"}:
        return "audio"
    if raw == "video":
        return "video"
    if raw in {"document", "file"}:
        return "document"
    return ""


def _url_from_block(block: Any) -> str:
    row = _as_dict(block)
    return str(row.get("url") or row.get("media_url") or row.get("download_url") or "").strip()


def attachments_from_content(content: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = content if isinstance(content, dict) else {}
    rows: list[dict[str, Any]] = []
    raw_attachments = data.get("attachments")
    if isinstance(raw_attachments, list):
        for item in raw_attachments:
            if isinstance(item, dict):
                rows.append(item)
    for kind, key in (("image", "image"), ("video", "video"), ("audio", "audio"), ("file", "document")):
        url = _url_from_block(data.get(key))
        if url:
            rows.append({"type": kind, "payload": {"url": url}})
    url = str(data.get("url") or data.get("media_url") or "").strip()
    if url and not rows:
        rows.append({"type": _kind_from_content(data) or "file", "payload": {"url": url}})
    return rows


async def hydrate_tiktok_inbound_media(*, tenant_id: str, content: dict[str, Any] | None) -> dict[str, Any]:
    attachments = attachments_from_content(content)
    caption = message_text_from_content(content)
    if attachments and tenant_id:
        from services.customer_reply_v2.inbound_media import ingest_inbound_attachments, luna_inbound_view

        result = await ingest_inbound_attachments(
            tenant_id=tenant_id,
            attachments=attachments,
            caption=caption,
        )
        return luna_inbound_view(result)
    return inbound_from_attachment_type(_kind_from_content(content or {}), transcript=caption)
