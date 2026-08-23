"""Shared Postgres cursors for Meta comment Graph polling."""

from __future__ import annotations

import json
from typing import Any

from services.tenant_runtime_config_service import load_sync_cursor, postgres_enabled, save_sync_cursor


def load_posts_cursor(binding_id: str) -> str | None:
    if not postgres_enabled():
        return None
    return load_sync_cursor(binding_id=binding_id, cursor_key="posts")


def save_posts_cursor(binding_id: str, cursor: str | None) -> None:
    if not postgres_enabled():
        return
    save_sync_cursor(
        binding_id=binding_id,
        cursor_key="posts",
        cursor_value=cursor or "",
        expected_revision=None,
    )


def load_seen_comment_ids(binding_id: str, post_id: str) -> set[str]:
    if not postgres_enabled():
        return set()
    raw = load_sync_cursor(binding_id=binding_id, cursor_key=f"seen:{post_id}")
    if not raw:
        return set()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload if str(item).strip()}


def save_seen_comment_ids(binding_id: str, post_id: str, comment_ids: set[str], *, limit: int = 500) -> None:
    if not postgres_enabled():
        return
    trimmed = sorted(comment_ids)[-limit:]
    save_sync_cursor(
        binding_id=binding_id,
        cursor_key=f"seen:{post_id}",
        cursor_value=json.dumps(trimmed),
        expected_revision=None,
    )


def extract_next_cursor(payload: dict[str, Any]) -> str | None:
    paging = payload.get("paging")
    if not isinstance(paging, dict):
        return None
    nxt = paging.get("next")
    return str(nxt) if nxt else None
