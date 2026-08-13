"""Smart Follow-Up analytics from durable PG events/jobs (tenant-scoped)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import (
    WhatsAppSmartFollowUpEvent,
    WhatsAppSmartFollowUpJob,
    WhatsAppSmartFollowUpSequence,
)


def _parse_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def build_smart_followup_analytics(
    session: Session,
    *,
    tenant_id: str,
    start: datetime,
    end: datetime,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    sequences_started = (
        session.scalar(
            select(func.count())
            .select_from(WhatsAppSmartFollowUpSequence)
            .where(
                WhatsAppSmartFollowUpSequence.tenant_id == tenant_id,
                WhatsAppSmartFollowUpSequence.created_at >= start,
                WhatsAppSmartFollowUpSequence.created_at < end,
            )
        )
        or 0
    )

    jobs = list(
        session.scalars(
            select(WhatsAppSmartFollowUpJob).where(
                WhatsAppSmartFollowUpJob.tenant_id == tenant_id,
                WhatsAppSmartFollowUpJob.created_at >= start,
                WhatsAppSmartFollowUpJob.created_at < end,
            )
        ).all()
    )

    sent = [j for j in jobs if j.status == "sent"]
    cancelled = [j for j in jobs if j.status == "cancelled"]
    skipped = [j for j in jobs if j.status == "skipped"]
    failed = [j for j in jobs if j.status in {"failed", "reconciliation_required"}]
    credits = sum(int(j.credits_captured or 0) for j in jobs)

    reply_events = (
        session.scalar(
            select(func.count())
            .select_from(WhatsAppSmartFollowUpEvent)
            .where(
                WhatsAppSmartFollowUpEvent.tenant_id == tenant_id,
                WhatsAppSmartFollowUpEvent.event_type == "sequence_cancelled",
                WhatsAppSmartFollowUpEvent.reason_code == "customer_reply",
                WhatsAppSmartFollowUpEvent.created_at >= start,
                WhatsAppSmartFollowUpEvent.created_at < end,
            )
        )
        or 0
    )

    by_step: dict[str, dict[str, int]] = {}
    by_channel: dict[str, dict[str, int]] = {}
    for j in jobs:
        key = str(j.step_index)
        bucket = by_step.setdefault(
            key,
            {"scheduled": 0, "sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "credits": 0},
        )
        bucket["scheduled"] += 1
        ch_bucket = by_channel.setdefault(
            str(j.channel or "whatsapp_cloud"),
            {"scheduled": 0, "sent": 0, "cancelled": 0, "skipped": 0, "failed": 0},
        )
        ch_bucket["scheduled"] += 1
        if j.status == "sent":
            bucket["sent"] += 1
            bucket["credits"] += int(j.credits_captured or 0)
            ch_bucket["sent"] += 1
        elif j.status == "cancelled":
            bucket["cancelled"] += 1
            ch_bucket["cancelled"] += 1
        elif j.status == "skipped":
            bucket["skipped"] += 1
            ch_bucket["skipped"] += 1
        elif j.status in {"failed", "reconciliation_required"}:
            bucket["failed"] += 1
            ch_bucket["failed"] += 1

    response_rate = (float(reply_events) / float(len(sent))) if sent else 0.0

    return {
        "success": True,
        "feature": "smart_followup",
        "availability": "ok",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": timezone_name,
        },
        "metrics": {
            "sequences_started": int(sequences_started),
            "followups_sent": len(sent),
            "cancelled": len(cancelled),
            "skipped": len(skipped),
            "failed_or_reconciliation": len(failed),
            "customer_replies_after_followup": int(reply_events),
            "response_rate": round(response_rate, 4),
            "ai_credits_consumed": int(credits),
            "by_step": by_step,
            "by_channel": by_channel,
            "whatsapp_delivery_cost": {
                "billing_mode": "customer_direct",
                "estimate_available": False,
                "manage_in_meta": True,
                "note": "WhatsApp delivery is billed by Meta to the customer payment method.",
            },
        },
    }


def resolve_analytics_window(
    *,
    period: str = "7d",
    timezone_name: str = "UTC",
    start_iso: str | None = None,
    end_iso: str | None = None,
) -> tuple[datetime, datetime, str]:
    tz = _parse_tz(timezone_name)
    now = datetime.now(tz)
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        return start.astimezone(UTC), end.astimezone(UTC), timezone_name

    days = 7
    if period.endswith("d") and period[:-1].isdigit():
        days = max(1, min(90, int(period[:-1])))
    elif period == "30d":
        days = 30
    elif period == "1d":
        days = 1
    end = now.astimezone(UTC)
    start = (now - __import__("datetime").timedelta(days=days)).astimezone(UTC)
    return start, end, timezone_name
