"""Read-through inject of recent public comment HISTORY into a later DM turn."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.brain.contracts.turn import ConversationState, CustomerTurn, HistorySnapshot
from services.brain.conversation_history import load_stored_history_rows
from services.brain.conversation_store import load_conversation, save_conversation
from services.brain.history import build_history_snapshot

_MAX_INJECT = 12
_PREFIXES = ("ig:", "instagram:", "fb:", "facebook:", "tiktok:", "tt:")

COMMENT_BRIDGE_POLICY_NOTE = (
    "HISTORY includes this customer's recent public comments on a post. Continue that "
    "topic. Do not re-ask facts they already gave in comments."
)


def platform_of_channel(channel: str) -> str:
    name = (channel or "").strip().lower()
    if name.startswith("instagram") or name in {"ig"}:
        return "instagram"
    if name.startswith("facebook") or name.startswith("messenger") or name in {"fb", "meta"}:
        return "facebook"
    if name.startswith("tiktok") or name in {"tt"}:
        return "tiktok"
    return ""


def normalize_author_id(raw: str) -> str:
    value = (raw or "").strip()
    lowered = value.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            return value[len(prefix) :].strip()
    return value


def _pointer_id(platform: str, author_id: str) -> str:
    return f"comment_bridge:{platform}:{author_id}"


def remember_comment_thread(turn: CustomerTurn) -> None:
    if (turn.surface or "") != "comment":
        return
    platform = platform_of_channel(turn.channel)
    author = normalize_author_id(turn.customer_id)
    conv = (turn.conversation_id or "").strip()
    if not platform or not author or not conv.startswith("comment:"):
        return
    post_id = str((turn.extra or {}).get("post_id") or "").strip()
    save_conversation(
        turn.tenant_id,
        _pointer_id(platform, author),
        ConversationState(),
        [],
        history=[
            {
                "id": conv,
                "role": "bridge",
                "text": post_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    )


def _bridge_rows(tenant_id: str, user_id: str, channel: str) -> list[dict[str, Any]]:
    platform = platform_of_channel(channel)
    author = normalize_author_id(user_id)
    if not platform or not author or not (tenant_id or "").strip():
        return []
    pointer = load_conversation(tenant_id, _pointer_id(platform, author)) or {}
    rows = [row for row in (pointer.get("history") or []) if isinstance(row, dict)]
    if not rows:
        return []
    comment_cid = str(rows[-1].get("id") or "").strip()
    if not comment_cid.startswith("comment:"):
        return []
    stored = load_stored_history_rows(tenant_id, comment_cid)
    out: list[dict[str, Any]] = []
    for row in stored[-_MAX_INJECT:]:
        text = str(row.get("text") or "").strip()
        role = str(row.get("role") or "user").strip() or "user"
        if not text:
            continue
        rid = str(row.get("id") or "").strip() or f"comment_bridge:{len(out)}"
        out.append(
            {
                "id": f"comment_bridge:{rid}",
                "role": role,
                "text": text,
                "timestamp": str(row.get("timestamp") or ""),
                "visible_to_customer": True,
            }
        )
    return out


def merge_comment_history_into_dm(
    history: HistorySnapshot,
    *,
    tenant_id: str,
    user_id: str,
    channel: str,
    current_inbound_id: str = "",
    current_inbound_text: str = "",
) -> tuple[HistorySnapshot, list[str]]:
    if (channel or "").strip().lower().endswith("_comment"):
        return history, []
    bridged = _bridge_rows(tenant_id, user_id, channel)
    if not bridged:
        return history, []
    existing_ids = {item.id for item in history.messages}
    prior = [row for row in bridged if str(row.get("id") or "") not in existing_ids]
    if not prior:
        return history, []
    merged = prior + [item.model_dump() for item in history.messages]
    snapshot = build_history_snapshot(
        merged,
        current_inbound_id=current_inbound_id,
        current_inbound_text=current_inbound_text,
    )
    return snapshot, [COMMENT_BRIDGE_POLICY_NOTE]
