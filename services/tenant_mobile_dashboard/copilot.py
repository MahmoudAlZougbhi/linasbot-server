"""Owner Copilot Dashboard stats: chats, credits, and per-user rows that add up."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from services.owner_ai_model_router import owner_chat_usage_tracker
from services.owner_chat_store import OwnerChatStore


def credits_from_tokens(tokens: int) -> int:
    if tokens <= 0:
        return 0
    return max(1, round(int(tokens) / 100))


def _safe_ts(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _display_name(user: dict[str, Any] | None, user_id: str) -> str:
    if isinstance(user, dict):
        for key in ("displayName", "name", "email"):
            raw = user.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()[:80]
    return user_id


def _lookup_names(user_ids: set[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    if not user_ids:
        return names
    try:
        from services.user_service import user_service

        for uid in user_ids:
            names[uid] = _display_name(user_service.get_user_by_id(uid), uid)
    except Exception:
        for uid in user_ids:
            names.setdefault(uid, uid)
    return names


def build_owner_copilot_summary(
    tenant_id: str,
    *,
    start_ts: float,
    end_ts: float,
    log_credits_by_conversation: dict[str, int],
    log_credits_unmapped: int,
    log_interactions: int,
    store: OwnerChatStore | None = None,
) -> dict[str, Any]:
    """Real Copilot spend for the selected range. Totals equal the sum of by_user rows."""
    tid = (tenant_id or "").strip().lower()
    chat_store = store or OwnerChatStore()
    chats_by_user: dict[str, int] = defaultdict(int)
    conv_to_user: dict[str, str] = {}

    for meta in chat_store.iter_tenant_conversation_meta(tid):
        uid = str(meta.get("user_id") or "").strip()
        cid = str(meta.get("id") or "").strip()
        if cid and uid:
            conv_to_user[cid] = uid
        if not meta.get("has_user_message"):
            continue
        active_at = max(_safe_ts(meta.get("updated_at")), _safe_ts(meta.get("created_at")))
        if active_at < start_ts or active_at >= end_ts:
            continue
        if uid:
            chats_by_user[uid] += 1

    credits_by_user: dict[str, int] = defaultdict(int)
    unattributed = max(0, int(log_credits_unmapped))
    tracker_convs: set[str] = set()
    sources: list[str] = []

    tracker_rows = owner_chat_usage_tracker.rows_in_window(tid, start_ts=start_ts, end_ts=end_ts)
    if tracker_rows:
        sources.append("owner_ai_usage")
    for row in tracker_rows:
        uid = str(row.get("user_id") or "").strip()
        cid = str(row.get("conversation_id") or "").strip()
        if cid:
            tracker_convs.add(cid)
        credits = credits_from_tokens(int(row.get("total_tokens") or 0))
        if uid:
            credits_by_user[uid] += credits
        else:
            unattributed += credits

    leftover_logs = 0
    for cid, credits in log_credits_by_conversation.items():
        if cid in tracker_convs:
            continue
        leftover_logs += int(credits)
        uid = conv_to_user.get(cid, "")
        if uid:
            credits_by_user[uid] += int(credits)
        else:
            unattributed += int(credits)
    if leftover_logs or log_credits_unmapped:
        sources.append("interaction_logs_estimate")

    user_ids: set[str] = set(chats_by_user) | set(credits_by_user)
    names = _lookup_names(user_ids)
    by_user: list[dict[str, Any]] = []
    for uid in sorted(user_ids, key=lambda key: cast(str, names.get(key, key)).lower()):
        by_user.append(
            {
                "user_id": uid,
                "name": names.get(uid, uid),
                "chats": int(chats_by_user.get(uid, 0)),
                "credits": int(credits_by_user.get(uid, 0)),
            }
        )
    if unattributed:
        by_user.append(
            {
                "user_id": None,
                "name": None,
                "chats": 0,
                "credits": int(unattributed),
                "unattributed": True,
            }
        )

    total_chats = sum(int(row["chats"]) for row in by_user)
    total_credits = sum(int(row["credits"]) for row in by_user)
    return {
        "credits": total_credits,
        "chats": total_chats,
        "users": len(user_ids),
        "by_user": by_user,
        "interactions": int(log_interactions),
        "credits_source": "+".join(sources) if sources else "none",
    }
