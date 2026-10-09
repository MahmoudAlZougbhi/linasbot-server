"""In-memory test posts. Nothing here calls Meta or TikTok."""

from __future__ import annotations

import uuid
from typing import Any

_POSTS: dict[str, dict[str, Any]] = {}
_EVENTS: list[dict[str, Any]] = []


def reset_lab() -> None:
    _POSTS.clear()
    _EVENTS.clear()


def create_post(*, tenant_id: str, platform: str, kind: str, caption: str) -> dict[str, Any]:
    post_id = f"sbx_post_{uuid.uuid4().hex}"
    row = {
        "id": post_id,
        "tenant_id": tenant_id,
        "platform": platform,
        "type": kind,
        "caption": caption,
        "label": "TEST – not published",
    }
    _POSTS[post_id] = row
    return row


def posts_for(tenant_id: str) -> list[dict[str, Any]]:
    return [row for row in _POSTS.values() if row["tenant_id"] == tenant_id]


def add_event(
    *,
    tenant_id: str,
    post_id: str | None,
    kind: str,
    text: str,
    auto_reply: bool,
) -> dict[str, Any]:
    post = _POSTS.get(post_id or "")
    if post_id and (post is None or post["tenant_id"] != tenant_id):
        raise PermissionError("not_found")
    if kind == "comment" and not auto_reply:
        action = "auto-reply off → left for staff"
        reply = ""
    elif kind == "dm" and "human" in text.casefold():
        action = "human handoff"
        reply = "Captured, not sent"
    else:
        action = "public reply" if kind == "comment" else "private dm"
        reply = "Captured, not sent"
    event = {
        "id": f"sbx_event_{uuid.uuid4().hex}",
        "tenant_id": tenant_id,
        "post_id": post_id,
        "kind": kind,
        "text": text,
        "action": action,
        "reply": reply,
        "charged_messages": 0,
        "ledger_reason": "sandbox",
    }
    _EVENTS.append(event)
    return event


def events_for(tenant_id: str, post_id: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in _EVENTS if row["tenant_id"] == tenant_id]
    if post_id:
        rows = [row for row in rows if row["post_id"] == post_id]
    return rows
