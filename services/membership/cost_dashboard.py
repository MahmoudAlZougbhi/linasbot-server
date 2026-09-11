"""Reconcile expense journal + message ledger for platform-admin views."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from services.membership.daily_edits import known_daily_edit_tenant_ids, status as daily_edit_status
from services.membership.expense_journal import ExpenseEvent, event_dict, known_total, list_events
from services.membership.message_ledger import known_ledger_tenant_ids, list_reservations, snapshot_dict
from services.membership.message_policy import ZERO_DEBIT
from services.membership.pg_store import store_backend

GENERATIVE_CLASSES = frozenset({"generated_ai", "mixed_faq_ai", "followup_sent"})
FAQ_STATIC_CLASSES = frozenset({"faq_only", "static", "resource_only"})

PLATFORM_TENANT = "__platform__"


def _sum_known(events: list[ExpenseEvent], key: str) -> dict[str, str]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for event in events:
        if event.status != "known" or event.amount_usd is None:
            continue
        totals[str(getattr(event, key) or "unspecified")] += event.amount_usd
    return {name: str(value) for name, value in sorted(totals.items())}


def _by_category(events: list[ExpenseEvent]) -> dict[str, str]:
    return _sum_known(events, "category")


def _by_feature(events: list[ExpenseEvent]) -> dict[str, str]:
    return _sum_known(events, "feature")


def _known_cost_tenant_ids(expense_tenant_ids: set[str]) -> list[str]:
    ids = set(expense_tenant_ids)
    ids.update(known_ledger_tenant_ids())
    from services.customer_ai.conversation_store import known_conversation_tenant_ids
    from services.customer_ai.outbox import known_outbox_tenant_ids
    from services.membership.credit_reservation_index import known_index_tenant_ids
    from services.membership.pending_settlement import known_settlement_tenant_ids
    from services.membership.processing_budgets import known_processing_tenant_ids

    ids.update(known_settlement_tenant_ids())
    ids.update(known_index_tenant_ids())
    ids.update(known_outbox_tenant_ids())
    ids.update(known_processing_tenant_ids())
    ids.update(known_daily_edit_tenant_ids())
    ids.update(known_conversation_tenant_ids())
    ids.discard("")
    ids.discard(PLATFORM_TENANT)
    return sorted(ids)


def _daily_edit_overview(tenant_ids: list[str]) -> dict[str, Any]:
    used = reserved = at_limit = 0
    rows: list[dict[str, Any]] = []
    for tenant_id in tenant_ids:
        state = daily_edit_status(tenant_id)
        used += state.used
        reserved += state.reserved
        if state.remaining <= 0:
            at_limit += 1
        rows.append(
            {
                "tenant_id": tenant_id,
                "used": state.used,
                "reserved": state.reserved,
                "remaining": state.remaining,
                "limit": state.limit,
                "reset_at": state.reset_at,
                "source": state.source,
            }
        )
    return {
        "used": used,
        "reserved": reserved,
        "tenants_at_limit": at_limit,
        "tenants": rows,
    }


def _by_tenant(events: list[ExpenseEvent]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ExpenseEvent]] = defaultdict(list)
    for event in events:
        grouped[event.tenant_id].append(event)
    rows = []
    for tenant_id, items in grouped.items():
        known = known_total(items)
        rows.append(
            {
                "tenant_id": tenant_id,
                "known_usd": str(known),
                "event_count": len(items),
                "pending": sum(1 for item in items if item.status in {"pending", "unpriced"}),
                "top_category": _largest_category(items),
            }
        )
    rows.sort(key=lambda row: Decimal(row["known_usd"]), reverse=True)
    return rows


def _largest_category(events: list[ExpenseEvent]) -> str:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for event in events:
        if event.status == "known" and event.amount_usd is not None:
            totals[event.category] += event.amount_usd
    if not totals:
        return ""
    return max(totals, key=totals.get)


def period_bounds(preset: str | None) -> tuple[str | None, str | None]:
    if not preset or preset in {"all", "custom"}:
        return None, None
    now = datetime.now(timezone.utc)
    today = now.date()
    start = today
    if preset == "yesterday":
        start = today - timedelta(days=1)
        end = start
        return f"{start.isoformat()}T00:00:00", f"{end.isoformat()}T23:59:59"
    if preset == "last_7_days":
        start = today - timedelta(days=6)
    elif preset == "last_30_days":
        start = today - timedelta(days=29)
    elif preset == "today":
        start = today
    else:
        return None, None
    return f"{start.isoformat()}T00:00:00", f"{today.isoformat()}T23:59:59"


def _filters(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value}


def _from_snapshot(snap: dict[str, Any]) -> dict[str, int]:
    allocated = sum(
        int(lot.get("granted") or 0)
        for lot in snap.get("lots") or []
        if lot.get("live", True)
    )
    remaining = int(snap.get("remaining") or 0)
    reserved = int(snap.get("reserved") or 0)
    return {
        "allocated": allocated,
        "used": max(0, allocated - remaining - reserved),
        "remaining": remaining,
        "reserved": reserved,
    }


def _message_totals(tenant_ids: list[str]) -> dict[str, int]:
    totals = {"allocated": 0, "used": 0, "remaining": 0, "reserved": 0}
    for tenant_id in tenant_ids:
        part = _from_snapshot(snapshot_dict(tenant_id))
        for key, value in part.items():
            totals[key] += value
    return totals


def _message_report(tenant_ids: list[str]) -> dict[str, Any]:
    from services.membership.message_flags import message_billing_enabled
    from services.membership.period_grants import ensure_included_grant

    active = message_billing_enabled()
    if active:
        for tenant_id in tenant_ids:
            ensure_included_grant(tenant_id)
    return {
        "message_billing_active": active,
        "note": (
            "Customer message units are separate from provider expense. "
            + (
                "Remaining is the live ledger after included grants."
                if active
                else "These figures are ledger rows only. Tenants do not see remaining until message billing is on."
            )
        ),
        **_message_totals(tenant_ids),
    }


def _stamp(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value or "")


def _in_window(created_at: Any, since: str | None, until: str | None) -> bool:
    if not since and not until:
        return True
    stamp = _stamp(created_at)
    if since and stamp < since:
        return False
    if until and stamp > until:
        return False
    return True


def _bucket() -> dict[str, int]:
    return {"count": 0, "units": 0, "settled_units": 0}


def usage_classes(
    tenant_id: str | None = None,
    *,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    by_class: dict[str, dict[str, int]] = {}
    generative = _bucket()
    faq_or_static = _bucket()
    other_zero = _bucket()
    for reservation in list_reservations(tenant_id):
        if not _in_window(reservation.created_at, since, until):
            continue
        name = reservation.response_class or "unspecified"
        row = by_class.setdefault(name, _bucket())
        row["count"] += 1
        row["units"] += int(reservation.units or 0)
        if reservation.status == "settled":
            row["settled_units"] += int(reservation.units or 0)
        target = other_zero
        if name in GENERATIVE_CLASSES:
            target = generative
        elif name in FAQ_STATIC_CLASSES:
            target = faq_or_static
        elif name in ZERO_DEBIT:
            target = other_zero
        else:
            target = generative if reservation.units else other_zero
        target["count"] += 1
        target["units"] += int(reservation.units or 0)
        if reservation.status == "settled":
            target["settled_units"] += int(reservation.units or 0)
    return {
        "generative": generative,
        "faq_or_static": faq_or_static,
        "other_zero": other_zero,
        "by_class": by_class,
        "note": "FAQ/static/resource-only settle at 0 message units. Generative and sent follow-up settle at 1.",
    }


def global_dashboard(
    *,
    environment: str | None = None,
    category: str | None = None,
    feature: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    events = list_events(
        environment=environment,
        **_filters(category=category, feature=feature, provider=provider, model=model, since=since, until=until),
    )
    tenant_events = [item for item in events if item.tenant_id != PLATFORM_TENANT]
    platform_events = [item for item in events if item.tenant_id == PLATFORM_TENANT]
    tenant_known = known_total(tenant_events)
    platform_known = known_total(platform_events)
    by_category = _by_category(events)
    tenant_ids = _known_cost_tenant_ids({item.tenant_id for item in tenant_events})
    from services.customer_ai.outbox import outbox_counts
    from services.membership.credit_reservation_index import open_counts as leftover_credit_counts
    from services.membership.pending_settlement import pending_counts
    from services.membership.processing_budgets import status as processing_status

    return {
        "audience": "platform_owner",
        "timezone": "UTC",
        "environment": environment,
        "store": store_backend(),
        "filters": {
            "category": category,
            "feature": feature,
            "provider": provider,
            "model": model,
            "since": since,
            "until": until,
        },
        "messages": _message_report(tenant_ids),
        "pending_settlements": pending_counts(),
        "leftover_credit_holds": leftover_credit_counts(),
        "outbox": outbox_counts(),
        "processing_budgets": processing_status(),
        "usage_classes": usage_classes(since=since, until=until),
        "known_usd": str(tenant_known + platform_known),
        "tenant_known_usd": str(tenant_known),
        "platform_shared_usd": str(platform_known),
        "pending_or_unpriced": sum(1 for item in events if item.status in {"pending", "unpriced"}),
        "by_category": by_category,
        "by_feature": _by_feature(events),
        "by_provider": _sum_known(events, "provider"),
        "by_model": _sum_known(events, "model"),
        "daily_edits": _daily_edit_overview(tenant_ids),
        "llm_total_excludes_translation": "translation" not in by_category or "llm_generation" in by_category,
        "tenants": _by_tenant(tenant_events),
        "reconciles": tenant_known + platform_known == known_total(events),
        "events": [event_dict(item) for item in events],
    }


def tenant_dashboard(
    tenant_id: str,
    *,
    environment: str | None = None,
    category: str | None = None,
    feature: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    tid = tenant_id.strip()
    events = list_events(
        tenant_id=tid,
        environment=environment,
        **_filters(category=category, feature=feature, provider=provider, model=model, since=since, until=until),
    )
    edits = daily_edit_status(tid)
    report = _message_report([tid])
    snap = snapshot_dict(tid)
    from services.customer_ai.outbox import outbox_counts
    from services.membership.credit_reservation_index import open_counts as leftover_credit_counts
    from services.membership.pending_settlement import pending_counts
    from services.membership.processing_budgets import status as processing_status

    return {
        "audience": "platform_owner",
        "tenant_id": tid,
        "store": store_backend(),
        "messages": {
            **snap,
            **report,
        },
        "pending_settlements": pending_counts(tenant_id=tid),
        "leftover_credit_holds": leftover_credit_counts(tenant_id=tid),
        "outbox": outbox_counts(tenant_id=tid),
        "processing_budgets": processing_status(tid),
        "usage_classes": usage_classes(tid, since=since, until=until),
        "known_usd": str(known_total(events)),
        "pending_or_unpriced": sum(1 for item in events if item.status in {"pending", "unpriced"}),
        "cost_status": "pending" if any(item.status in {"pending", "unpriced"} for item in events) else "known",
        "by_category": _by_category(events),
        "by_feature": _by_feature(events),
        "by_provider": _sum_known(events, "provider"),
        "by_model": _sum_known(events, "model"),
        "top_category": _largest_category(events),
        "filters": {
            "category": category,
            "feature": feature,
            "provider": provider,
            "model": model,
            "since": since,
            "until": until,
        },
        "daily_edits": {
            "limit": edits.limit,
            "used": edits.used,
            "reserved": edits.reserved,
            "remaining": edits.remaining,
            "reset_at": edits.reset_at,
            "source": edits.source,
        },
        "events": [event_dict(item) for item in events],
    }
