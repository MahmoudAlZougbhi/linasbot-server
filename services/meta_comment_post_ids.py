"""Facebook/Instagram comment webhooks must bind to the post, not the parent comment."""

from __future__ import annotations

from typing import Any


def facebook_post_id_from_compound(raw: str) -> str:
    """Page post ids are ``{page}_{post}``. Comment ids add a third segment."""

    parts = [part for part in str(raw or "").split("_") if part]
    if len(parts) < 2:
        return ""
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return ""
    return f"{parts[0]}_{parts[1]}"


def facebook_post_id_from_feed_value(value: dict[str, Any]) -> str:
    """Never treat a nested ``parent_id`` comment as the post."""

    for key in ("post_id", "photo_id", "video_id", "share_id"):
        explicit = str(value.get(key) or "").strip()
        if explicit:
            return explicit
    parent_id = str(value.get("parent_id") or "").strip()
    return facebook_post_id_from_compound(parent_id)


def comment_post_id_keys(post_id: str) -> set[str]:
    raw = str(post_id or "").strip()
    if not raw:
        return set()
    keys = {raw}
    compound = facebook_post_id_from_compound(raw)
    if compound:
        keys.add(compound)
        suffix = compound.split("_", 1)[-1]
        if suffix:
            keys.add(suffix)
    return keys


def comment_post_ids_match(left: str, right: str) -> bool:
    if not str(left or "").strip() or not str(right or "").strip():
        return False
    if str(left).strip() == str(right).strip():
        return True
    return bool(comment_post_id_keys(left) & comment_post_id_keys(right))
