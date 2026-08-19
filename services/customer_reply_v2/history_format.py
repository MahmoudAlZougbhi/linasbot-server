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
    nearby_replies: list[Any] | None = None,
    comment_id: str = "",
    post_id: str = "",
    now_ts: float | None = None,
    current_author_id: str = "",
    current_author_name: str = "",
    nearby_reply_records: list[dict[str, Any]] | None = None,
    parent_author_id: str = "",
    parent_author_name: str = "",
) -> list[dict[str, Any]]:
    """Same-post thread context with author labels. Does not mix the whole post into one identity."""
    _ = post_id
    records: list[dict[str, Any]] = []
    ts = now_ts
    if parent_comment:
        records.append(
            history_record(
                role="user",
                text=_label_thread_text(
                    str(parent_comment),
                    author_id=parent_author_id,
                    author_name=parent_author_name,
                    current_author_id=current_author_id,
                    from_page=False,
                ),
                timestamp=ts,
                channel=channel,
                message_id="",
            )
        )
    structured = list(nearby_reply_records or [])
    if structured:
        for row in structured[:8]:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            from_page = bool(row.get("from_page"))
            records.append(
                history_record(
                    role="assistant" if from_page else "user",
                    text=_label_thread_text(
                        text,
                        author_id=str(row.get("author_id") or ""),
                        author_name=str(row.get("author_name") or ""),
                        current_author_id=current_author_id,
                        from_page=from_page,
                    ),
                    timestamp=ts,
                    channel=channel,
                    message_id=str(row.get("comment_id") or ""),
                )
            )
    else:
        for reply in list(nearby_replies or [])[:8]:
            if isinstance(reply, dict):
                text = str(reply.get("text") or "").strip()
                if not text:
                    continue
                from_page = bool(reply.get("from_page"))
                records.append(
                    history_record(
                        role="assistant" if from_page else "user",
                        text=_label_thread_text(
                            text,
                            author_id=str(reply.get("author_id") or ""),
                            author_name=str(reply.get("author_name") or ""),
                            current_author_id=current_author_id,
                            from_page=from_page,
                        ),
                        timestamp=ts,
                        channel=channel,
                    )
                )
                continue
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
                text=_label_thread_text(
                    comment_text,
                    author_id=current_author_id,
                    author_name=current_author_name,
                    current_author_id=current_author_id,
                    from_page=False,
                    is_current=True,
                ),
                timestamp=ts,
                channel=channel,
                message_id=comment_id,
            )
        )
    return records


def _label_thread_text(
    text: str,
    *,
    author_id: str,
    author_name: str,
    current_author_id: str,
    from_page: bool,
    is_current: bool = False,
) -> str:
    name = (author_name or author_id or "participant").strip()
    if is_current:
        return f"[current_author {name}] {text}" if name else text
    if from_page:
        return f"[page_reply] {text}"
    if current_author_id and author_id and author_id != current_author_id:
        return f"[other_participant {name}] {text}"
    if current_author_id and author_id and author_id == current_author_id:
        return f"[same_author {name}] {text}"
    return text


def same_history_for_agents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy used by both Luna and Tera — identical order and fields."""
    return [dict(item) for item in records]
