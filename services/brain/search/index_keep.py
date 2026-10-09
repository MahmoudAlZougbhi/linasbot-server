"""A failed refresh must not hide an index that already worked."""

from __future__ import annotations


def index_reply_mode(*, has_previous: bool, refresh_failed: bool) -> str:
    if refresh_failed and has_previous:
        return "previous"
    if refresh_failed:
        return "closed"
    return "current"
