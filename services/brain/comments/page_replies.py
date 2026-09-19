"""Remember public page/AI comment ids so nested replies can detect 'reply to us'."""

from __future__ import annotations

from services.brain.conversation_history import append_visible_history, load_stored_history_rows

_SKIP_IDS = frozenset({"", "simulated", "simulated_both"})


def _conversation_id(channel: str) -> str:
    ch = (channel or "").strip() or "comment"
    return f"page_comment_replies:{ch}"


def remember_page_comment_reply(*, tenant_id: str, channel: str, reply_id: str) -> None:
    tid = (tenant_id or "").strip()
    rid = (reply_id or "").strip()
    if not tid or rid in _SKIP_IDS:
        return
    append_visible_history(
        tid,
        _conversation_id(channel),
        [{"id": rid, "role": "assistant", "text": "page_reply"}],
    )


def is_page_comment_reply(*, tenant_id: str, channel: str, comment_id: str) -> bool:
    tid = (tenant_id or "").strip()
    cid = (comment_id or "").strip()
    if not tid or not cid:
        return False
    rows = load_stored_history_rows(tid, _conversation_id(channel))
    return any(str(row.get("id") or "").strip() == cid for row in rows)
