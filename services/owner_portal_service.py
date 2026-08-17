"""Read models for the authenticated Linas.ai platform-owner portal."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from services.billing_backend import billing_uses_postgres, require_billing_pg_session
from services.interaction_flow_logger import get_recent_flows
from services.user_service import user_service
from storage.persistent_storage import _DATA_ROOT

_RANGE_DAYS = {
    "last_day": 1,
    "last_7_days": 7,
    "last_month": 30,
    "last_6_months": 183,
    "last_year": 365,
}


def _range_start(range_key: str, now: datetime) -> datetime:
    if range_key == "last_week":
        this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return this_monday - timedelta(days=7)
    days = _RANGE_DAYS.get(range_key)
    if days is None:
        raise ValueError("Unsupported date range")
    return now - timedelta(days=days)


def _in_range(value: Any, start: datetime, end: datetime) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return start <= parsed.astimezone(UTC) < end
    except (TypeError, ValueError):
        return False


def _billing_by_tenant(tenant_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not tenant_ids:
        return {}
    if billing_uses_postgres():
        from sqlalchemy import select

        from db.models.credit_entitlements import CreditBalanceRow, TenantEntitlementRow

        with require_billing_pg_session() as session:
            rows = session.execute(
                select(TenantEntitlementRow, CreditBalanceRow)
                .outerjoin(CreditBalanceRow, CreditBalanceRow.tenant_id == TenantEntitlementRow.tenant_id)
                .where(TenantEntitlementRow.tenant_id.in_(tenant_ids))
            ).all()
        return {
            ent.tenant_id: {
                "plan_id": ent.plan_id,
                "subscription_status": ent.status,
                "included_credits": int(ent.included_credits or 0),
                "extra_credits": int(ent.extra_credits or 0),
                "credits_remaining": int(balance.available or 0)
                if balance is not None
                else int((ent.included_credits or 0) + (ent.extra_credits or 0)),
            }
            for ent, balance in rows
        }

    import json

    output: dict[str, dict[str, Any]] = {}
    ent_root = Path(_DATA_ROOT) / "entitlements"
    balance_root = Path(_DATA_ROOT) / "credit_ledger"
    for tenant_id in tenant_ids:
        ent_path = ent_root / f"{tenant_id}.json"
        if not ent_path.is_file():
            continue
        try:
            ent = json.loads(ent_path.read_text(encoding="utf-8"))
            balance_path = balance_root / f"{tenant_id}.balance.json"
            balance = json.loads(balance_path.read_text(encoding="utf-8")) if balance_path.is_file() else {}
            included = int(ent.get("included_credits") or 0)
            extra = int(ent.get("extra_credits") or 0)
            output[tenant_id] = {
                "plan_id": ent.get("plan_id") or "none",
                "subscription_status": ent.get("status") or "none",
                "included_credits": included,
                "extra_credits": extra,
                "credits_remaining": int(balance.get("available", included + extra)),
            }
        except (OSError, ValueError, TypeError):
            continue
    return output


def list_subscribers(users: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One Firestore scan plus one batched billing query; no per-row reads."""
    users = user_service.get_all_users() if users is None else users
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for user in users:
        tenant_id = str(user.get("tenantId") or "").strip()
        if tenant_id:
            grouped[tenant_id].append(user)
    billing = _billing_by_tenant(set(grouped))
    rows: list[dict[str, Any]] = []
    for tenant_id, members in grouped.items():
        bill = billing.get(tenant_id, {})
        total_credits = int(bill.get("included_credits") or 0) + int(bill.get("extra_credits") or 0)
        remaining = int(bill.get("credits_remaining") or 0)
        primary = next((u for u in members if u.get("role") in {"owner", "admin"}), members[0])
        rows.append(
            {
                "tenant_id": tenant_id,
                "email": primary.get("email"),
                "business_name": primary.get("businessName"),
                "subscription": bill.get("plan_id") or "none",
                "membership": bill.get("subscription_status") or "none",
                "seats_created": len(members),
                "roles": sorted({str(u.get("role") or "viewer") for u in members}),
                "status": primary.get("status") or "unknown",
                "credits_total": total_credits,
                "credits_used": max(0, total_credits - remaining),
                "credits_remaining": remaining,
                "users": members,
            }
        )
    return sorted(rows, key=lambda row: (str(row["business_name"] or "").lower(), row["tenant_id"]))


def analytics(range_key: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    start = _range_start(range_key, now)
    end = now
    if range_key == "last_week":
        end = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    users = user_service.get_all_users()
    flows = [row for row in get_recent_flows(limit=500) if _in_range(row.get("timestamp"), start, end)]
    channels = Counter(str(row.get("channel") or "unknown") for row in flows)
    message_types = Counter(str(row.get("message_type") or "text") for row in flows)
    subscribers = list_subscribers(users)
    active_subscribers = [r for r in subscribers if r["membership"] in {"active", "trial", "grace"}]
    return {
        "range": range_key,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "new_users": sum(1 for user in users if _in_range(user.get("createdAt"), start, end)),
        "live_users": sum(1 for user in users if _in_range(user.get("lastLogin"), start, end)),
        "subscribers": len(active_subscribers),
        "messages_by_channel": dict(channels),
        "comments": int(message_types.get("comment", 0)),
        "credits_total": sum(int(row["credits_total"]) for row in active_subscribers),
        "credits_used": sum(int(row["credits_used"]) for row in active_subscribers),
        "credits_remaining": sum(int(row["credits_remaining"]) for row in active_subscribers),
        "coverage": {
            "users": "Firestore dashboard users",
            "billing": "tenant entitlements + credit balances",
            "messages": "bounded Interaction Logs (latest 500 rows); not a full historical aggregate",
            "tiktok": "blocked: no TikTok interaction source exists",
        },
    }
