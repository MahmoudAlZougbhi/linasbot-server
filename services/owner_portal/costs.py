"""Platform Owner cost dashboards. Billing remains the ledger/cost source of truth."""

from __future__ import annotations

from typing import Any

from services.billing.membership.conversion_dry_run import dry_run_credit_inventory
from services.billing.membership.cost_dashboard import global_dashboard, period_bounds, tenant_dashboard
from services.billing.membership.message_ledger import snapshot_dict
from services.billing.membership.reconcile import ledger_health
from services.brain.search.force_reindex import force_reindex_tenant


def platform_costs(
    *,
    environment: str | None = None,
    category: str | None = None,
    feature: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    start, end = period_bounds(period)
    env = (environment or "").strip() or None
    return global_dashboard(
        environment=env,
        category=category,
        feature=feature,
        provider=provider,
        model=model,
        since=since or start,
        until=until or end,
    )


def tenant_costs(
    tenant_id: str,
    *,
    environment: str | None = None,
    category: str | None = None,
    feature: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    start, end = period_bounds(period)
    env = (environment or "").strip() or None
    return tenant_dashboard(
        tenant_id,
        environment=env,
        category=category,
        feature=feature,
        provider=provider,
        model=model,
        since=since or start,
        until=until or end,
    )


def credit_conversion_dry_run() -> dict[str, Any]:
    return dry_run_credit_inventory()


def message_ledger(tenant_id: str) -> dict[str, Any]:
    tid = tenant_id.strip()
    if not tid:
        raise ValueError("tenant_id is required")
    return {"ledger": snapshot_dict(tid), "health": ledger_health(tid)}


async def reindex_customer_ai(tenant_id: str) -> dict[str, Any]:
    tid = tenant_id.strip()
    if not tid:
        raise ValueError("tenant_id is required")
    return await force_reindex_tenant(tid)
