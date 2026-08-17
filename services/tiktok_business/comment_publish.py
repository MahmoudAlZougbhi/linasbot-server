"""Publish TikTok comment replies via Manage Account Comment."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.http_client import tiktok_request


async def create_comment_reply(
    *,
    access_token: str,
    business_id: str,
    video_id: str,
    comment_id: str,
    text: str,
) -> dict[str, Any]:
    body = {
        "business_id": business_id,
        "video_id": video_id,
        "comment_id": comment_id,
        "text": text,
    }
    return await tiktok_request(
        method="POST",
        path="/business/comment/reply/create/",
        access_token=access_token,
        json_body=body,
    )
