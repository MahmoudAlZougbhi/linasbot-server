"""Meta comment Graph poll is removed. Inbound comments are webhook-only."""

from __future__ import annotations


def meta_comment_poll_enabled() -> bool:
    """Always off. META_COMMENT_POLL_ENABLED is ignored."""
    return False


async def run_meta_social_comment_sync_job() -> None:
    return
