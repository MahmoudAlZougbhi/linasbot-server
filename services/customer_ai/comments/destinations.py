"""Extract comment/DM destinations from a Brain outcome. Senders must honor these."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommentDestinations:
    public_text: str = ""
    private_text: str = ""
    comment_mode: str = ""
    public_depends_on_private: bool = False

    @property
    def has_any(self) -> bool:
        return bool(self.public_text or self.private_text)


def coerce_comment_destinations(value: Any) -> CommentDestinations | None:
    if value is None:
        return None
    if isinstance(value, CommentDestinations):
        return value
    if isinstance(value, str):
        text = value.strip()
        return CommentDestinations(public_text=text) if text else None
    return None


def destinations_from_outcome(outcome: Any) -> CommentDestinations:
    meta = getattr(outcome, "metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    public = str(meta.get("public_comment_text") or "").strip()
    private = str(meta.get("private_dm_text") or "").strip()
    mode = str(meta.get("comment_mode") or "")
    depends = False
    for item in meta.get("outbound_messages") or []:
        if not isinstance(item, dict):
            continue
        dest = str(item.get("destination") or "")
        text = str(item.get("text") or "").strip()
        if dest == "comment" and text and not public:
            public = text
        if dest == "dm" and text and not private:
            private = text
        if dest == "comment" and "private" in (item.get("depends_on") or []):
            depends = True
    if not public and not private:
        public = str(getattr(outcome, "reply", None) or "").strip()
    return CommentDestinations(
        public_text=public[:900],
        private_text=private[:900],
        comment_mode=mode,
        public_depends_on_private=depends,
    )


def public_text_for_channel(plan: CommentDestinations, *, private_send_possible: bool) -> str:
    """Do not post a public DM claim when this channel cannot send the private first."""
    if plan.public_depends_on_private and not private_send_possible:
        return ""
    return plan.public_text
