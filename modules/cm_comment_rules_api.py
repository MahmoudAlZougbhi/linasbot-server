"""Comment Rule preview + connected post picker APIs (session tenant only)."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Request

from modules.api_security import require_session
from modules.core import app
from services.customer_reply_v2.comment_rule_engine import preview_comment_rule
from services.customer_reply_v2.connected_posts import list_connected_posts, list_tenant_comment_accounts


@app.get("/api/cm/comment-rules/accounts")
async def comment_rule_accounts(request: Request) -> Any:
    session = require_session(request)
    return {"success": True, "accounts": list_tenant_comment_accounts(session.tenant_id)}


@app.get("/api/cm/comment-rules/posts")
async def comment_rule_posts(
    request: Request,
    platform: str = "",
    connected_account_id: str = "",
    after: str = "",
    limit: int = 25,
) -> Any:
    session = require_session(request)
    result = await list_connected_posts(
        tenant_id=session.tenant_id,
        platform=platform,
        connected_account_id=connected_account_id,
        after=after,
        limit=limit,
    )
    return {"success": bool(result.get("ok")), **result}


@app.post("/api/cm/comment-rules/preview")
async def comment_rule_preview(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    _ = session.tenant_id
    raw_rule = body.get("rule")
    rule: dict[str, Any] = dict(raw_rule) if isinstance(raw_rule, dict) else {}
    preview = preview_comment_rule(
        rule,
        comment_text=str(body.get("comment_text") or ""),
        post_id=str(body.get("post_id") or ""),
        channel=str(body.get("channel") or ""),
        account_id=str(body.get("account_id") or ""),
    )
    return {"success": True, "preview": preview}
