"""Tenant interaction usage aggregation from activity_flow (no USD costs)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from services.interaction_flow_logger import FLOW_LOG_FILE, _tail_lines
from services.wallet_spend_analytics import _entry_matches_tenant, _parse_ts
from storage.persistent_storage import ACTIVITY_FLOW_FILE

_USAGE_MAX_BYTES = 8 * 1024 * 1024
_USAGE_MAX_LINES = 50_000

USAGE_BUCKETS = (
    "instagram_dm",
    "facebook_dm",
    "instagram_comments",
    "facebook_comments",
    "whatsapp_dm",
    "owner_copilot",
    "content_management_ai",
    "other",
)


def _normalize_usage_bucket(entry: dict[str, Any]) -> str:
    channel = str(entry.get("channel") or "").strip().lower()
    source = str(entry.get("source") or "").strip().lower()
    handler = str(entry.get("handler_path") or "").strip().lower()
    outcome = str(entry.get("outcome") or "").strip().lower()

    if channel in {"instagram_comment", "instagram_comments"}:
        return "instagram_comments"
    if channel in {"facebook_comment", "facebook_comments"}:
        return "facebook_comments"
    if "comment" in channel or "comment" in handler:
        if "instagram" in channel or "instagram" in handler:
            return "instagram_comments"
        if "facebook" in channel or "facebook" in handler or "messenger" in channel:
            return "facebook_comments"
    if channel in {"instagram", "ig"}:
        return "instagram_dm"
    if channel in {"facebook", "messenger", "fb"}:
        return "facebook_dm"
    if channel in {"whatsapp", "whatsapp_dm", "wa"} or "whatsapp" in handler:
        return "whatsapp_dm"
    if channel in {"owner", "owner_copilot", "dashboard"} or "owner" in handler or "owner_ai" in source:
        return "owner_copilot"
    if source.startswith("cm_") or "cm_runtime" in source or "content_management" in handler:
        return "content_management_ai"
    if channel in {"testing_lab", "test"} and "owner" in outcome:
        return "owner_copilot"
    return "other"


def _load_entries(log_path: str | None = None) -> list[dict[str, Any]]:
    path = log_path or str(ACTIVITY_FLOW_FILE) or FLOW_LOG_FILE
    lines = _tail_lines(path, _USAGE_MAX_LINES, max_bytes=_USAGE_MAX_BYTES)
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _is_failure(entry: dict[str, Any]) -> bool:
    if entry.get("flow_error"):
        return True
    outcome = str(entry.get("outcome") or "").strip().lower()
    if outcome in {"error", "failed", "failure", "handoff_failed"}:
        return True
    source = str(entry.get("source") or "").strip().lower()
    return source in {"rate_limit", "moderation", "error"}


def aggregate_tenant_usage(
    tenant_id: str,
    *,
    start_ts: float,
    end_ts: float,
    entries: list[dict[str, Any]] | None = None,
    log_path: str | None = None,
) -> dict[str, Any]:
    """Count interactions for a tenant window. Never invents zeros for missing credit attribution."""
    tid = (tenant_id or "").strip().lower()
    scoped = [e for e in (entries if entries is not None else _load_entries(log_path)) if _entry_matches_tenant(e, tid)]
    start = datetime.fromtimestamp(start_ts, tz=UTC)
    end = datetime.fromtimestamp(end_ts, tz=UTC)

    by_bucket: dict[str, dict[str, int]] = {key: {"interactions": 0, "failed": 0} for key in USAGE_BUCKETS}
    daily: dict[str, int] = defaultdict(int)
    total = 0
    failed = 0
    success = 0

    for entry in scoped:
        ts = _parse_ts(entry.get("timestamp"))
        if ts is None or ts < start or ts >= end:
            continue
        total += 1
        bucket = _normalize_usage_bucket(entry)
        if bucket not in by_bucket:
            bucket = "other"
        by_bucket[bucket]["interactions"] += 1
        if _is_failure(entry):
            failed += 1
            by_bucket[bucket]["failed"] += 1
        else:
            success += 1
        day_key = ts.astimezone(UTC).strftime("%Y-%m-%d")
        daily[day_key] += 1

    series = [{"date": day, "interactions": daily[day]} for day in sorted(daily.keys())]
    distribution = [
        {
            "bucket": key,
            "interactions": by_bucket[key]["interactions"],
            "failed": by_bucket[key]["failed"],
            "credits": None,
            "credits_available": False,
        }
        for key in USAGE_BUCKETS
        if by_bucket[key]["interactions"] > 0 or key != "other"
    ]
    # Keep stable order; drop empty "other" only.
    distribution = [row for row in distribution if row["bucket"] != "other" or int(row["interactions"] or 0) > 0]

    return {
        "status": "ok" if total > 0 else "empty",
        "source": "interaction_logs",
        "total_interactions": total,
        "successful_interactions": success,
        "failed_interactions": failed,
        "success_rate": (success / total) if total else None,
        "instagram_dms": by_bucket["instagram_dm"]["interactions"],
        "facebook_dms": by_bucket["facebook_dm"]["interactions"],
        "instagram_comments": by_bucket["instagram_comments"]["interactions"],
        "facebook_comments": by_bucket["facebook_comments"]["interactions"],
        "owner_copilot": by_bucket["owner_copilot"]["interactions"],
        "content_management_ai": by_bucket["content_management_ai"]["interactions"],
        "other": by_bucket["other"]["interactions"],
        "time_series": series,
        "distribution": distribution,
        "credits_by_bucket_available": False,
        "credits_by_bucket_note": (
            "Per-bucket credit attribution is not available from the current file credit ledger; "
            "period credit totals come from the entitlement/ledger balance."
        ),
    }
