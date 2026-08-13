"""Dashboard activity totals and per-channel breakdown for the mobile UI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from services.tenant_mobile_dashboard.usage import _is_failure, _load_entries, _normalize_usage_bucket
from services.wallet_spend_analytics import _entry_matches_tenant, _parse_ts

_ACTIVITY_PLATFORMS = ("instagram", "facebook", "tiktok", "whatsapp")
_SMART_SOURCES = frozenset({"qa_database", "dynamic_retrieval"})
_REQUEST_CHANNEL_MAP = {
    "instagram_dm": "instagram",
    "facebook_messenger": "facebook",
    "whatsapp_cloud": "whatsapp",
    "comment_linked_dm": "instagram",
}


def _empty_platform_row() -> dict[str, int]:
    return {"messages": 0, "comments": 0, "smart": 0, "requests": 0, "credits": 0}


def _normalize_platform(channel: Any) -> str | None:
    ch = str(channel or "").strip().lower()
    if ch in {"instagram", "ig"}:
        return "instagram"
    if ch in {"facebook", "messenger", "fb"}:
        return "facebook"
    if ch in {"whatsapp", "wa", "whatsapp_dm", "360dialog", "dialog360"}:
        return "whatsapp"
    if ch in {"tiktok"}:
        return "tiktok"
    if "instagram" in ch:
        return "instagram"
    if "facebook" in ch or "messenger" in ch:
        return "facebook"
    if "whatsapp" in ch:
        return "whatsapp"
    return None


def _entry_tokens(entry: dict[str, Any]) -> int:
    if isinstance(entry.get("tokens"), int):
        return max(0, int(entry["tokens"]))
    prompt = entry.get("prompt_tokens")
    completion = entry.get("completion_tokens")
    total = 0
    if isinstance(prompt, int):
        total += max(0, prompt)
    if isinstance(completion, int):
        total += max(0, completion)
    return total


def _entry_credits_estimate(entry: dict[str, Any]) -> int:
    cost = entry.get("cost_usd")
    if isinstance(cost, (int, float)) and float(cost) > 0:
        return max(1, round(float(cost) * 1000))
    tokens = _entry_tokens(entry)
    if tokens > 0:
        return max(1, round(tokens / 100))
    return 0


def _is_reply(entry: dict[str, Any]) -> bool:
    if _is_failure(entry):
        return False
    if entry.get("bot_to_user"):
        return True
    outcome = str(entry.get("outcome") or "").strip().lower()
    return outcome not in {"", "error", "failed", "failure", "handoff_failed"}


def _request_counts_by_platform(
    tenant_id: str,
    *,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, int], int, str]:
    try:
        from sqlalchemy import func, select

        from db.models.requests import CustomerRequest
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        with whatsapp_session() as session:
            stmt = (
                select(CustomerRequest.source_channel, func.count())
                .where(
                    CustomerRequest.tenant_id == tenant_id,
                    CustomerRequest.created_at >= start,
                    CustomerRequest.created_at < end,
                )
                .group_by(CustomerRequest.source_channel)
            )
            rows = session.execute(stmt).all()
        by_platform = {key: 0 for key in _ACTIVITY_PLATFORMS}
        total = 0
        for channel, count in rows:
            platform = _REQUEST_CHANNEL_MAP.get(str(channel or ""))
            n = int(count or 0)
            total += n
            if platform in by_platform:
                by_platform[platform] += n
        return by_platform, total, "customer_requests_db"
    except WhatsAppDatabaseUnavailable:
        return {key: 0 for key in _ACTIVITY_PLATFORMS}, 0, "unavailable"
    except Exception:
        return {key: 0 for key in _ACTIVITY_PLATFORMS}, 0, "unavailable"


def _owner_copilot_stats(
    tenant_id: str,
    *,
    start_ts: float,
    end_ts: float,
    owner_copilot_interactions: int,
    owner_copilot_credits: int,
) -> dict[str, Any]:
    chats = 0
    users: set[str] = set()
    try:
        from pathlib import Path

        from services.owner_chat_store import OwnerChatStore

        store = OwnerChatStore()
        tenant_dir: Path = store._tenant_dir(tenant_id)
        for path in tenant_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("deleted"):
                continue
            updated = float(data.get("updated_at") or 0)
            created = float(data.get("created_at") or 0)
            active_at = max(updated, created)
            if active_at < start_ts or active_at >= end_ts:
                continue
            chats += 1
            uid = str(data.get("user_id") or "").strip()
            if uid:
                users.add(uid)
    except Exception:
        pass
    return {
        "credits": owner_copilot_credits,
        "chats": chats,
        "users": len(users),
        "interactions": owner_copilot_interactions,
        "credits_source": "interaction_logs_estimate" if owner_copilot_credits else "none",
    }


def build_activity_summary(
    tenant_id: str,
    *,
    start_ts: float,
    end_ts: float,
    integrations: list[dict[str, Any]],
    entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip().lower()
    start = datetime.fromtimestamp(start_ts, tz=UTC)
    end = datetime.fromtimestamp(end_ts, tz=UTC)
    scoped = [
        e
        for e in (entries if entries is not None else _load_entries())
        if _entry_matches_tenant(e, tid)
    ]

    platform_rows = {key: _empty_platform_row() for key in _ACTIVITY_PLATFORMS}
    owner_copilot_credits = 0
    owner_copilot_interactions = 0

    for entry in scoped:
        ts = _parse_ts(entry.get("timestamp"))
        if ts is None or ts < start or ts >= end:
            continue
        if not _is_reply(entry):
            continue

        bucket = _normalize_usage_bucket(entry)
        platform = _normalize_platform(entry.get("channel"))
        source = str(entry.get("source") or "").strip().lower()
        credits = _entry_credits_estimate(entry)

        if bucket == "owner_copilot":
            owner_copilot_interactions += 1
            owner_copilot_credits += credits
            continue

        if platform not in platform_rows:
            continue

        if bucket in {"instagram_dm", "facebook_dm", "whatsapp_dm"}:
            platform_rows[platform]["messages"] += 1
        elif bucket in {"instagram_comments", "facebook_comments"}:
            platform_rows[platform]["comments"] += 1

        if source in _SMART_SOURCES:
            platform_rows[platform]["smart"] += 1

        platform_rows[platform]["credits"] += credits

    req_by_platform, req_total, req_source = _request_counts_by_platform(tid, start=start, end=end)
    for platform, count in req_by_platform.items():
        platform_rows[platform]["requests"] = count

    connected = {
        str(row.get("platform") or ""): bool(row.get("connected"))
        for row in integrations
        if isinstance(row, dict)
    }

    channels: list[dict[str, Any]] = []
    for platform in _ACTIVITY_PLATFORMS:
        is_connected = bool(connected.get(platform))
        coming_soon = platform == "tiktok" and not is_connected
        if platform == "tiktok" and not is_connected:
            continue
        row = platform_rows[platform]
        channels.append(
            {
                "platform": platform,
                "connected": is_connected,
                "operational": is_connected,
                "coming_soon": coming_soon,
                **row,
            }
        )

    total_messages = sum(platform_rows[p]["messages"] for p in _ACTIVITY_PLATFORMS)
    total_comments = sum(platform_rows[p]["comments"] for p in _ACTIVITY_PLATFORMS)
    total_smart = sum(platform_rows[p]["smart"] for p in _ACTIVITY_PLATFORMS)

    return {
        "availability": "ok",
        "total_activity": {
            "messages_replied": total_messages,
            "comments_replied": total_comments,
            "smart_answers": total_smart,
            "requests": req_total,
        },
        "channels": channels,
        "owner_copilot": _owner_copilot_stats(
            tid,
            start_ts=start_ts,
            end_ts=end_ts,
            owner_copilot_interactions=owner_copilot_interactions,
            owner_copilot_credits=owner_copilot_credits,
        ),
        "requests_source": req_source,
        "credits_by_channel_note": (
            "Per-channel credits are estimated from interaction token/cost fields in activity logs."
        ),
    }
