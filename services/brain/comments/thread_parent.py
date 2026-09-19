"""Classify comment parents from Graph/TikTok edges. No content lexicons."""

from __future__ import annotations

from typing import Literal

from services.ai_setup.comment_rules import published_replies_to_any_comments

ParentKind = Literal["top_level", "page", "human", "same_author", "unknown"]

JOINER_POLICY_NOTE = (
    "This customer replied to the page on a public comment thread that already had "
    "another public exchange. Answer this customer only. Do not import another "
    "commenter's private conversation."
)


def _id_set(values: set[str] | tuple[str, ...] | list[str]) -> set[str]:
    return {str(item or "").strip() for item in values if str(item or "").strip()}


def classify_comment_parent(
    *,
    parent_id: str = "",
    post_id: str = "",
    parent_from_id: str = "",
    owner_ids: set[str] | tuple[str, ...] | list[str] | None = None,
    parent_is_page_reply: bool = False,
    current_author_id: str = "",
) -> ParentKind:
    parent = (parent_id or "").strip()
    post = (post_id or "").strip()
    if not parent or parent in {"0", "0.0"} or (post and parent == post):
        return "top_level"
    owners = _id_set(owner_ids or set())
    parent_from = (parent_from_id or "").strip()
    author = (current_author_id or "").strip()
    if parent_is_page_reply or (parent_from and parent_from in owners):
        return "page"
    if parent_from and author and parent_from == author:
        return "same_author"
    if parent_from and parent_from not in owners:
        return "human"
    return "unknown"


def skip_third_party_join(
    kind: ParentKind,
    *,
    tenant_id: str = "",
    channel: str = "",
    post_id: str = "",
) -> bool:
    """Human-to-human nested replies are not our turn unless the owner opted into all comments."""
    if kind != "human":
        return False
    return not published_replies_to_any_comments(tenant_id, channel=channel, post_id=post_id)


def joiner_policy_notes(*, kind: ParentKind, prior_history_count: int = 0) -> list[str]:
    if kind == "page" and int(prior_history_count or 0) <= 0:
        return [JOINER_POLICY_NOTE]
    return []
