"""Read models for the authenticated Linas.ai platform-owner portal."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from services.billing.billing_backend import billing_uses_postgres, require_billing_pg_session
from services.team.user_service import user_service
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
            # Copy columns before the session closes. Reading them afterwards
            # raises DetachedInstanceError and the overview comes back empty.
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
    if users is None:
        from services.team.user_tenant_query import list_users_capped

        users = list_users_capped(user_service, limit=200)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for user in users:
        tenant_id = str(user.get("tenantId") or "").strip()
        if tenant_id:
            grouped[tenant_id].append(user)
    billing = _billing_by_tenant(set(grouped))
    rows: list[dict[str, Any]] = []
    for tenant_id, members in grouped.items():
        bill = billing.get(tenant_id, {})
        remaining = int(bill.get("credits_remaining") or 0)
        primary = next((u for u in members if u.get("role") in {"owner", "admin"}), members[0])
        plan_id = str(bill.get("plan_id") or "none")
        from services.billing.credit_ai_gate import remaining_messages
        from services.billing.membership.message_ledger import snapshot

        snap = snapshot(tenant_id)
        msg_remaining = remaining_messages(tenant_id)
        granted = int(snap.included) + int(snap.purchased)
        rows.append(
            {
                "tenant_id": tenant_id,
                "email": primary.get("email"),
                "business_name": primary.get("businessName"),
                "subscription": plan_id,
                "membership": bill.get("subscription_status") or "none",
                "seats_created": len(members),
                "roles": sorted({str(u.get("role") or "viewer") for u in members}),
                "status": primary.get("status") or "unknown",
                "credits_total": granted,
                "credits_used": max(0, granted - msg_remaining),
                "credits_remaining": msg_remaining,
                "messages_total": granted,
                "messages_used": max(0, granted - msg_remaining),
                "messages_remaining": msg_remaining,
                "message_remaining": msg_remaining,
                "historical_credit_remaining": remaining,
                "hide_by_default": _hide_tenant(
                    tenant_id=tenant_id,
                    business_name=str(primary.get("businessName") or ""),
                    email=str(primary.get("email") or ""),
                    status=str(primary.get("status") or ""),
                ),
                **_catalog_offer(plan_id),
                "users": members,
            }
        )
    return sorted(rows, key=lambda row: (str(row["business_name"] or "").lower(), row["tenant_id"]))


def _hide_tenant(*, tenant_id: str, business_name: str, email: str, status: str) -> bool:
    from services.team.tenant_identity import is_junk_identity

    if status.strip().lower() == "blocked":
        return True
    return is_junk_identity(tenant_id=tenant_id, business_name=business_name, email=email)


def _catalog_offer(plan_id: str) -> dict[str, Any]:
    from services.billing.membership.catalog_admin import effective_included_messages
    from services.billing.membership.catalog_revenue import intended_price_usd

    try:
        included = effective_included_messages(plan_id)
    except Exception:
        included = None
    return {
        "intended_included_messages": included,
        "intended_price_usd": intended_price_usd(plan_id),
    }


def _catalog_revenue(plan_ids: list[str]) -> dict[str, Any]:
    from services.billing.membership.catalog_revenue import revenue_pair

    return revenue_pair(plan_ids)


def _subscriber_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Same credit and message definitions as the Users rows."""
    active = [row for row in rows if row.get("membership") in {"active", "trial", "grace"}]

    def _num(row: dict[str, Any], key: str, fallback: str) -> int:
        raw = row.get(key, row.get(fallback, 0))
        return int(raw or 0)

    return {
        "subscribers": len(active),
        "credits_total": sum(_num(row, "credits_total", "credits_total") for row in active),
        "credits_used": sum(_num(row, "credits_used", "credits_used") for row in active),
        "credits_remaining": sum(_num(row, "credits_remaining", "credits_remaining") for row in active),
        "messages_total": sum(_num(row, "messages_total", "credits_total") for row in active),
        "messages_used": sum(_num(row, "messages_used", "credits_used") for row in active),
        "messages_remaining": sum(_num(row, "messages_remaining", "credits_remaining") for row in active),
        "historical_credit_remaining": sum(int(row.get("historical_credit_remaining") or 0) for row in active),
    }


def analytics(range_key: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    start = _range_start(range_key, now)
    end = now
    if range_key == "last_week":
        end = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    from services.owner_portal.flow_counts import channel_counts_for_range
    from services.team.user_tenant_query import list_users_capped

    counted = channel_counts_for_range(start, end)
    channels = Counter(counted["messages_by_channel"])
    comments = int(counted["comments"])
    from services.owner_portal.analytics_sql import load_overview

    sql = load_overview(start, end)
    if sql is not None:
        totals = sql
        plan_ids = list(sql["plan_ids"])
        coverage_users = "Postgres dashboard users"
        coverage_billing = "tenant entitlements and message lots"
    else:
        users = list_users_capped(user_service, limit=500)
        subscribers = list_subscribers(users)
        active = [row for row in subscribers if row["membership"] in {"active", "trial", "grace"}]
        totals = {
            "new_users": sum(1 for user in users if _in_range(user.get("createdAt"), start, end)),
            "live_users": sum(1 for user in users if _in_range(user.get("lastLogin"), start, end)),
            "subscribers": len(active),
            "credits_total": sum(int(row["credits_total"]) for row in active),
            "credits_used": sum(int(row["credits_used"]) for row in active),
            "credits_remaining": sum(int(row["credits_remaining"]) for row in active),
            "messages_total": sum(int(row.get("messages_total", row["credits_total"])) for row in active),
            "messages_used": sum(int(row.get("messages_used", row["credits_used"])) for row in active),
            "messages_remaining": sum(int(row.get("messages_remaining", row["credits_remaining"])) for row in active),
        }
        plan_ids = [str(row["subscription"] or "") for row in active]
        coverage_users = "dashboard user documents"
        coverage_billing = "tenant entitlements + message ledger"
    billing_rows = list_subscribers(list_users_capped(user_service, limit=500))
    totals.update(_subscriber_totals(billing_rows))
    active_plans = [
        str(row.get("subscription") or "")
        for row in billing_rows
        if row.get("membership") in {"active", "trial", "grace"}
    ]
    if active_plans:
        plan_ids = active_plans
    return {
        "range": range_key,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "new_users": totals["new_users"],
        "live_users": totals["live_users"],
        "subscribers": totals["subscribers"],
        "messages_by_channel": dict(channels),
        "comments": comments,
        "credits_total": totals["credits_total"],
        "credits_used": totals["credits_used"],
        "credits_remaining": totals["credits_remaining"],
        "messages_total": totals["messages_total"],
        "messages_used": totals["messages_used"],
        "messages_remaining": totals["messages_remaining"],
        "historical_credit_remaining": totals.get("historical_credit_remaining", 0),
        **_catalog_revenue(plan_ids),
        "coverage": {
            "users": coverage_users,
            "billing": coverage_billing,
            "messages": "interaction logs in the selected range",
            "tiktok": "stored TikTok comments/DMs + interaction logs when connected",
            "revenue": "live_checkout_mrr_usd and intended_message_mrr_usd both use the credit plan catalog.",
        },
    }
