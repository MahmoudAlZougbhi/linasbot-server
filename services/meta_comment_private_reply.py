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


def _safe_graph_failure(status_code: int, body: dict[str, Any]) -> tuple[str, dict[str, int]]:
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = error.get("code") if isinstance(error, dict) else None
    subcode = error.get("error_subcode") if isinstance(error, dict) else None
    safe_code = int(code) if isinstance(code, int) and not isinstance(code, bool) else 0
    safe_subcode = int(subcode) if isinstance(subcode, int) and not isinstance(subcode, bool) else 0
    reason = f"graph_http_{int(status_code)}_code_{safe_code}_subcode_{safe_subcode}"
    return reason, {"code": safe_code, "error_subcode": safe_subcode}


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
        body = {}
    if not isinstance(body, dict):
        body = {}

    if response.status_code < 200 or response.status_code >= 300 or body.get("error"):
        reason, safe_error = _safe_graph_failure(response.status_code, body)
        _runtime_logger.warning(
            "[meta-comment] private_reply_failed channel=%s reason=%s",
            binding.channel,
            reason,
        )
        return False, reason, {"error": safe_error}

    reply_id = str(body.get("id") or body.get("message_id") or "").strip()
    if not reply_id:
        _runtime_logger.warning(
            "[meta-comment] private_reply_failed channel=%s reason=missing_reply_id",
            binding.channel,
        )
        return False, "missing_reply_id", {}

    return True, "sent", body
