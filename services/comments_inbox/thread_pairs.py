"""Pair customer comments with the page/IG reply when one exists."""

from __future__ import annotations

from typing import Any


def comment_text(row: dict[str, Any]) -> str:
    return str(row.get("text") or row.get("message") or "").strip()


def comment_from_raw(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("from")
    return raw if isinstance(raw, dict) else {}


def comment_author(row: dict[str, Any]) -> str:
    from_raw = comment_from_raw(row)
    return str(row.get("username") or from_raw.get("username") or from_raw.get("name") or "").strip()


def comment_from_id(row: dict[str, Any]) -> str:
    return str(comment_from_raw(row).get("id") or "").strip()


def is_self_comment(row: dict[str, Any], *, names: set[str], ids: set[str]) -> bool:
    username = comment_author(row).casefold()
    from_id = comment_from_id(row)
    return bool((username and username in names) or (from_id and from_id in ids))


def parent_id_of(row: dict[str, Any]) -> str:
    parent = row.get("parent")
    if isinstance(parent, dict):
        return str(parent.get("id") or "").strip()
    return str(row.get("parent_id") or "").strip()


def nested_replies(row: dict[str, Any], *, platform: str) -> list[dict[str, Any]]:
    nested = row.get("replies") if platform == "instagram" else row.get("comments")
    data = nested.get("data") if isinstance(nested, dict) else []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def first_self_reply(rows: list[dict[str, Any]], *, names: set[str], ids: set[str]) -> str:
    for row in rows:
        if is_self_comment(row, names=names, ids=ids):
            text = comment_text(row)
            if text:
                return text
    return ""


def pair_comment_threads(
    rows: list[Any],
    *,
    platform: str,
    media_id: str,
    names: set[str],
    ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    media = str(media_id or "").strip()
    by_parent: dict[str, list[dict[str, Any]]] = {}
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clean.append(row)
        parent = parent_id_of(row)
        if parent and parent != media:
            by_parent.setdefault(parent, []).append(row)

    out: list[dict[str, Any]] = []
    for row in clean:
        if is_self_comment(row, names=names, ids=ids):
            continue
        comment_id = str(row.get("id") or "").strip()
        text = comment_text(row)
        if not comment_id and not text:
            continue
        reply_pool = nested_replies(row, platform=platform) + by_parent.get(comment_id, [])
        ai_reply = first_self_reply(reply_pool, names=names, ids=ids)
        out.append(
            {
                "comment_id": comment_id,
                "author": comment_author(row),
                "comment": text,
                "ai_reply": ai_reply,
                "created_at": str(row.get("timestamp") or row.get("created_time") or ""),
                "delivery_status": "sent" if ai_reply else "none",
            }
        )
        if len(out) >= limit:
            break
    return out


def pair_tiktok_threads(rows: list[Any], *, post_id: str, limit: int) -> list[dict[str, Any]]:
    want = str(post_id or "").strip()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("post_id") or "") != want:
            continue
        if str(row.get("parent_comment_id") or "").strip():
            continue
        comment_id = str(row.get("comment_id") or "").strip()
        text = str(row.get("text") or "").strip()
        if not comment_id and not text:
            continue
        reply = str(row.get("ai_reply") or "").strip()
        status = str(row.get("delivery_status") or "").strip() or ("sent" if reply else "none")
        out.append(
            {
                "comment_id": comment_id,
                "author": str(row.get("author_username") or ""),
                "comment": text,
                "ai_reply": reply,
                "created_at": str(row.get("create_time") or ""),
                "delivery_status": status,
            }
        )
        if len(out) >= limit:
            break
    return out
