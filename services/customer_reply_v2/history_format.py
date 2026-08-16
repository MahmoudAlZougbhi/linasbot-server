"""Timestamped conversation history shared by Luna and Tera."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.customer_reply_v2.channel_metadata import parse_channel
from services.customer_reply_v2.models import ConversationWindow


def _iso_utc(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError):
        return None


def _sender_for_role(role: str) -> str:
    r = (role or "").strip().lower()
    if r in {"assistant", "ai", "business"}:
        return "business"
    return "customer"


def history_record(
    *,
    role: str,
    text: str,
    timestamp: float | None,
    channel: str,
    message_id: str = "",
    attachment_type: str | None = None,
    reply_to: dict[str, Any] | None = None,
) -> dict[str, Any]:
    platform, surface, _is_public = parse_channel(channel)
    return {
        "timestamp": _iso_utc(timestamp),
        "timestamp_unix": timestamp,
        "platform": platform,
        "surface": surface,
        "sender": _sender_for_role(role),
        "role": role,
        "message_id": message_id or None,
        "text": text,
        "attachment_type": attachment_type,
        "reply_to": reply_to,
    }


def history_records_from_window(
    window: ConversationWindow,
    *,
    channel: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if window.context_compacted and window.compacted_summary:
        records.append(
            history_record(
                role="system",
                text=f"Earlier conversation summary: {window.compacted_summary}",
                timestamp=None,
                channel=channel,
            )
        )
    for msg in window.messages:
        records.append(
            history_record(
                role=msg.role,
                text=msg.content,
                timestamp=msg.timestamp,
                channel=channel,
            )
        )
    return records


def history_records_from_raw(
    messages: list[dict[str, Any]],
    *,
    channel: str,
) -> list[dict[str, Any]]:
    """Normalize already-built window messages or OpenAI-like dicts."""
    out: list[dict[str, Any]] = []
    for raw in messages or []:
        if not isinstance(raw, dict):
            continue
        if "text" in raw and "surface" in raw:
            out.append(dict(raw))
            continue
        role = str(raw.get("role") or "user")
        text = str(raw.get("text") or raw.get("content") or "")
        ts = raw.get("timestamp_unix")
        if ts is None:
            ts = raw.get("timestamp")
        unix: float | None
        try:
            unix = float(ts) if ts is not None and not isinstance(ts, str) else None
        except (TypeError, ValueError):
            unix = None
        if unix is None and isinstance(ts, str) and ts.strip():
            try:
                unix = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                unix = None
        out.append(
            history_record(
                role=role,
                text=text,
                timestamp=unix,
                channel=channel,
                message_id=str(raw.get("message_id") or ""),
                attachment_type=raw.get("attachment_type"),
                reply_to=raw.get("reply_to") if isinstance(raw.get("reply_to"), dict) else None,
            )
        )
    return out


def comment_thread_records(
    *,
    channel: str,
    comment_text: str,
    parent_comment: str = "",
    nearby_replies: list[str] | None = None,
    comment_id: str = "",
    post_id: str = "",
    now_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Minimal same-post thread context for comments (no cross-post mix)."""
    _ = post_id
    records: list[dict[str, Any]] = []
    ts = now_ts
    if parent_comment:
        records.append(
            history_record(
                role="user",
                text=str(parent_comment),
                timestamp=ts,
                channel=channel,
                message_id="",
            )
        )
    for reply in list(nearby_replies or [])[:8]:
        if not str(reply).strip():
            continue
        records.append(
            history_record(
                role="assistant",
                text=str(reply),
                timestamp=ts,
                channel=channel,
            )
        )
    if comment_text:
        records.append(
            history_record(
                role="user",
                text=comment_text,
                timestamp=ts,
                channel=channel,
                message_id=comment_id,
            )
        )
    return records


def same_history_for_agents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy used by both Luna and Tera — identical order and fields."""
    return [dict(item) for item in records]
