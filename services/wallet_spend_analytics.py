"""Spend analytics for Token Wallet — aggregates Interaction Logs (activity flow).

Honest aggregation only: missing historical cost/channel fields are reported as
unavailable rather than invented.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from services.interaction_flow_logger import FLOW_LOG_FILE, _tail_lines
from storage.persistent_storage import ACTIVITY_FLOW_FILE

# Cap how much history we scan for analytics (bytes of the jsonl tail).
_ANALYTICS_MAX_BYTES = 8 * 1024 * 1024
_ANALYTICS_MAX_LINES = 50_000


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
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


def _entry_cost_usd(entry: dict[str, Any]) -> float | None:
    raw = entry.get("cost_usd")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _normalize_channel(raw: Any) -> str:
    ch = str(raw or "").strip().lower()
    if ch in ("instagram", "ig"):
        return "instagram"
    if ch in ("facebook", "messenger", "fb"):
        return "facebook"
    if ch in ("testing_lab", "dashboard", "test"):
        return "testing_lab"
    if ch in ("whatsapp", "wa", "360dialog", "dialog360"):
        return "whatsapp"
    if ch in ("web", "web_chat", "website"):
        return "web"
    if not ch or ch == "unknown":
        return "unknown"
    return ch


def _entry_matches_tenant(entry: dict[str, Any], tenant_id: str) -> bool:
    """Match entry tenant; unlabeled historical rows match only explicit linas queries."""
    tid = str(tenant_id or "").strip().lower()
    if not tid:
        raise ValueError("tenant_id required")
    raw = entry.get("tenant_id")
    if raw is None or str(raw).strip() == "":
        # Historical activity rows predating tenant tagging: attribute only when
        # the caller intentionally queries the founder clinic tenant.
        return tid == "linas"
    return str(raw).strip().lower() == tid


def _load_entries(path: str | None = None) -> list[dict[str, Any]]:
    log_path = path or str(ACTIVITY_FLOW_FILE) or FLOW_LOG_FILE
    if not os.path.isfile(log_path):
        return []
    lines = _tail_lines(log_path, _ANALYTICS_MAX_LINES, max_bytes=_ANALYTICS_MAX_BYTES)
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _period_bucket() -> tuple[datetime, datetime, datetime, datetime]:
    """Return (current_start, current_end, prior_start, prior_end) as UTC datetimes.

    Labels: trailing 12 months + prior 12 months (honest, not calendar-year).
    """
    now = datetime.now(UTC)
    current_end = now
    current_start = now - timedelta(days=365)
    prior_end = current_start
    prior_start = current_start - timedelta(days=365)
    return current_start, current_end, prior_start, prior_end


def _empty_channel_breakdown() -> dict[str, dict[str, Any]]:
    keys = ("facebook", "instagram", "testing_lab", "whatsapp", "unknown", "other")
    return {
        key: {
            "tokens": 0,
            "cost_usd": 0.0,
            "interactions": 0,
            "cost_available": False,
        }
        for key in keys
    }


def _summarize_period(
    entries: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    by_channel = _empty_channel_breakdown()
    conv_spend: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"tokens": 0, "cost_usd": 0.0, "interactions": 0, "cost_available": False}
    )
    total_tokens = 0
    total_cost = 0.0
    cost_rows = 0
    interactions = 0
    oldest: datetime | None = None
    newest: datetime | None = None
    rows_without_cost = 0
    rows_without_channel = 0

    for entry in entries:
        ts = _parse_ts(entry.get("timestamp"))
        if ts is None or ts < start or ts >= end:
            continue
        interactions += 1
        oldest = ts if oldest is None or ts < oldest else oldest
        newest = ts if newest is None or ts > newest else newest

        tokens = _entry_tokens(entry)
        total_tokens += tokens
        cost = _entry_cost_usd(entry)
        if cost is None:
            rows_without_cost += 1
        else:
            total_cost += cost
            cost_rows += 1

        channel = _normalize_channel(entry.get("channel"))
        if channel == "unknown":
            rows_without_channel += 1
        bucket_key = channel if channel in by_channel else "other"
        bucket = by_channel[bucket_key]
        bucket["tokens"] += tokens
        bucket["interactions"] += 1
        if cost is not None:
            bucket["cost_usd"] += cost
            bucket["cost_available"] = True

        conv_id = str(entry.get("conversation_id") or "").strip() or None
        if not conv_id:
            # Fall back to masked user identity so top-chat still works when
            # conversation_id was not persisted on older rows.
            conv_id = str(entry.get("user_id") or entry.get("user_id_masked") or "unknown")
        c = conv_spend[conv_id]
        c["tokens"] += tokens
        c["interactions"] += 1
        if cost is not None:
            c["cost_usd"] += cost
            c["cost_available"] = True
        c["channel"] = channel
        c["conversation_id"] = conv_id

    top_conversations: list[dict[str, Any]] = []
    for conv_id, stats in conv_spend.items():
        top_conversations.append(
            {
                "conversation_id": conv_id,
                "channel": stats.get("channel") or "unknown",
                "tokens": int(stats["tokens"]),
                "cost_usd": round(float(stats["cost_usd"]), 6),
                "interactions": int(stats["interactions"]),
                "cost_available": bool(stats["cost_available"]),
            }
        )
    top_conversations.sort(
        key=lambda row: (row["cost_usd"] if row["cost_available"] else 0.0, row["tokens"]),
        reverse=True,
    )

    for _key, bucket in by_channel.items():
        bucket["cost_usd"] = round(float(bucket["cost_usd"]), 6)
        bucket["tokens"] = int(bucket["tokens"])
        bucket["interactions"] = int(bucket["interactions"])

    return {
        "label": "trailing_12_months",
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
        "interactions": interactions,
        "tokens": total_tokens,
        "cost_usd": round(total_cost, 6),
        "cost_available": cost_rows > 0,
        "rows_without_cost": rows_without_cost,
        "rows_without_channel": rows_without_channel,
        "oldest_entry": oldest.isoformat().replace("+00:00", "Z") if oldest else None,
        "newest_entry": newest.isoformat().replace("+00:00", "Z") if newest else None,
        "by_channel": by_channel,
        "top_conversations": top_conversations[:10],
        "incomplete_history": interactions == 0,
    }


def build_wallet_spend_analytics(
    tenant_id: str,
    *,
    entries: list[dict[str, Any]] | None = None,
    log_path: str | None = None,
) -> dict[str, Any]:
    """Aggregate FB/IG/Testing Lab spend for trailing + prior 12 months."""
    tid = str(tenant_id or "").strip().lower()
    if not tid:
        raise ValueError("tenant_id required")
    current_start, current_end, prior_start, prior_end = _period_bucket()
    all_entries = entries if entries is not None else _load_entries(log_path)
    scoped = [e for e in all_entries if _entry_matches_tenant(e, tid)]

    current = _summarize_period(scoped, current_start, current_end)
    current["label"] = "trailing_12_months"
    current["display_label"] = "Last 12 months"

    prior = _summarize_period(scoped, prior_start, prior_end)
    prior["label"] = "prior_12_months"
    prior["display_label"] = "Previous 12 months"

    # Honest note when older period has no usable rows.
    notes: list[str] = []
    if prior["interactions"] == 0:
        notes.append("Spend for the previous 12 months is unavailable (no Interaction Log rows in that window).")
    if current["rows_without_cost"] and current["interactions"]:
        notes.append("Some Interaction Log rows lack cost estimates; USD totals only include rows with recorded cost.")
    if current["rows_without_channel"] and current["interactions"]:
        notes.append("Some older rows lack a channel label and are counted under Unknown.")

    return {
        "success": True,
        "tenant_id": tid,
        "source": "interaction_logs",
        "periods": {
            "trailing_12_months": current,
            "prior_12_months": prior,
        },
        "notes": notes,
        "interaction_logs_path": "/activity-flow",
    }
