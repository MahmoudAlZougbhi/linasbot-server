"""Meta private reply (comment → DM) via Graph API.

Facebook: POST /{comment-id}/private_replies
Instagram: POST /{ig-user-id}/messages with recipient.comment_id

No public-comment fallback when private reply fails.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from services.meta_app_registry import MetaAssetBinding
from services.meta_graph_routing import graph_api_url

_runtime_logger = logging.getLogger("uvicorn.error")


async def send_comment_private_reply(
    client: httpx.AsyncClient,
    *,
    binding: MetaAssetBinding,
    comment_id: str,
    message: str,
    token: str,
    graph_api_version: str,
) -> tuple[bool, str, dict[str, Any]]:
    """Send a private DM in response to a public comment. Returns (ok, reason, response)."""
    text = (message or "").strip()
    if not text:
        return False, "empty_private_reply", {}
    cid = (comment_id or "").strip()
    if not cid:
        return False, "missing_comment_id", {}

    version = graph_api_version or "v24.0"

    if binding.channel == "facebook":
        url = graph_api_url(binding, graph_api_version=version, path=f"{cid}/private_replies")
        response = await client.post(
            url,
            data={"message": text},
            headers={"Authorization": f"Bearer {token}"},
        )
    else:
        account_id = (binding.instagram_account_id or binding.asset_id or "").strip()
        if not account_id:
            return False, "missing_instagram_account", {}
        url = graph_api_url(binding, graph_api_version=version, path=f"{account_id}/messages")
        response = await client.post(
            url,
            json={
                "recipient": {"comment_id": cid},
                "message": {"text": text},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    try:
        body = response.json()
    except Exception:
        body = {"raw": (response.text or "")[:500]}
    if not isinstance(body, dict):
        body = {"value": body}

    if response.status_code >= 400:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or body["error"].get("code") or "")
        reason = err or f"http_{response.status_code}"
        _runtime_logger.warning(
            "[meta-comment] private_reply_failed channel=%s reason=%s",
            binding.channel,
            reason,
        )
        return False, reason, body

    return True, "sent", body
