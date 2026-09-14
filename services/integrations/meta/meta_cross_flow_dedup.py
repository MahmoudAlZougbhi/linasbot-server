"""Cross-auth-flow deduplication keys for Meta social events."""

from __future__ import annotations

GLOBAL_DM_CLAIM_NAMESPACE = "meta_social_dm_global"
GLOBAL_COMMENT_CLAIM_NAMESPACE = "meta_social_comment_global"


def global_dm_claim_key(event: dict) -> str:
    channel = str(event.get("channel") or "").strip().lower()
    account_id = str(event.get("account_id") or event.get("recipient_id") or "").strip()
    message_id = str(event.get("message_id") or "").strip()
    return f"{channel}:{account_id}:{message_id}"


def global_comment_claim_key(event: dict) -> str:
    channel = str(event.get("channel") or "").strip().lower()
    account_id = str(event.get("account_id") or "").strip()
    comment_id = str(event.get("comment_id") or "").strip()
    return f"{channel}:{account_id}:{comment_id}"
