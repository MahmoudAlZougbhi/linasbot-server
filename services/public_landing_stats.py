"""Public marketing aggregates for the Linas AI landing page.

Counts only. No PII. Cached so the public poll cannot scan logs on every hit.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.billing_backend import BillingBackendError, billing_uses_postgres
from services.tenant_mobile_dashboard.activity import _is_reply, _normalize_platform
from services.tenant_mobile_dashboard.usage import _load_entries, _normalize_usage_bucket
from storage.persistent_storage import _DATA_ROOT

_ACTIVE_STATUSES = frozenset({"active", "trial", "grace"})
_DM_BUCKETS = frozenset({"instagram_dm", "facebook_dm", "whatsapp_dm", "web_dm"})
_COMMENT_BUCKETS = frozenset({"instagram_comments", "facebook_comments"})
_CACHE_TTL_SECONDS = 20.0
_REFRESH_SECONDS = 20

_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _count_file_subscribers(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        status = str(data.get("status") or "").strip().lower()
        plan_id = str(data.get("plan_id") or "").strip().lower()
        if status in _ACTIVE_STATUSES and plan_id not in {"", "none"}:
            total += 1
    return total


def _count_businesses(*, entitlements_root: Path | None) -> tuple[int | None, str]:
    if entitlements_root is not None:
        return _count_file_subscribers(entitlements_root), "entitlements_files"
    if billing_uses_postgres():
        try:
            from services.billing_backend import require_billing_pg_session
            from services.entitlements_pg_store import count_active_subscribers

            with require_billing_pg_session() as session:
                return count_active_subscribers(session), "entitlements_postgres"
        except BillingBackendError:
            return None, "unavailable"
        except Exception:
            return None, "unavailable"
    return _count_file_subscribers(Path(_DATA_ROOT) / "entitlements"), "entitlements_files"


def _count_requests() -> tuple[int | None, str]:
    try:
        from sqlalchemy import func, select

        from db.models.requests import CustomerRequest
        from db.session import whatsapp_session

        with whatsapp_session(require=True) as session:
            total = session.execute(select(func.count()).select_from(CustomerRequest)).scalar_one()
        return int(total or 0), "customer_requests_db"
    except Exception:
        return None, "unavailable"


def _classify_reply(entry: dict[str, Any]) -> str | None:
    if not _is_reply(entry):
        return None
    bucket = _normalize_usage_bucket(entry)
    if bucket in _DM_BUCKETS:
        return "message"
    if bucket in _COMMENT_BUCKETS:
        return "comment"
    channel = str(entry.get("channel") or "").strip().lower()
    platform = _normalize_platform(channel)
    if platform == "tiktok":
        return "comment" if "comment" in channel else "message"
    return None


def _activity_from_logs(log_path: str | None) -> dict[str, Any]:
    entries = _load_entries(log_path)
    messages = 0
    comments = 0
    for entry in entries:
        kind = _classify_reply(entry)
        if kind == "message":
            messages += 1
        elif kind == "comment":
            comments += 1
    return {
        "messages_replied": messages,
        "comments_replied": comments,
        "ai_replies": messages + comments,
        "activity_source": "interaction_logs",
        "scanned_entries": len(entries),
    }


def collect_public_landing_stats(
    *,
    entitlements_root: Path | None = None,
    log_path: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Safe public payload: subscriber + AI-reply aggregates only."""
    global _cache
    bypass_cache = entitlements_root is not None or log_path is not None or not use_cache
    now = time.monotonic()
    if not bypass_cache:
        with _lock:
            if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
                return dict(_cache[1])

    businesses, businesses_source = _count_businesses(entitlements_root=entitlements_root)
    requests_count, requests_source = _count_requests()
    activity = _activity_from_logs(log_path)
    payload: dict[str, Any] = {
        "success": True,
        "businesses_using_linas": businesses,
        "businesses_source": businesses_source,
        "messages_replied": activity["messages_replied"],
        "comments_replied": activity["comments_replied"],
        "ai_replies": activity["ai_replies"],
        "activity_source": activity["activity_source"],
        "scanned_entries": activity["scanned_entries"],
        "requests": requests_count,
        "requests_source": requests_source,
        "refresh_seconds": _REFRESH_SECONDS,
        "generated_at": _iso_now(),
    }
    if not bypass_cache:
        with _lock:
            _cache = (time.monotonic(), dict(payload))
    return payload


def reset_public_landing_stats_cache() -> None:
    global _cache
    with _lock:
        _cache = None
