"""Pending provider-cost rows. Never invent USD and never debit messages."""

from __future__ import annotations

from typing import Any

from services.membership.expense_journal import ExpenseCategory, record_expense


def record_pending_provider(
    *,
    event_id: str,
    tenant_id: str,
    category: ExpenseCategory,
    feature: str,
    provider: str,
    model: str,
    quantity: int | float = 1,
    operation_id: str = "",
) -> Any | None:
    tid = (tenant_id or "").strip()
    if not tid or not event_id:
        return None
    try:
        return record_expense(
            event_id=event_id,
            tenant_id=tid,
            category=category,
            feature=feature,
            provider=provider,
            model=model,
            amount_usd=None,
            quantity=quantity,
            status="pending",
            operation_id=operation_id,
        )
    except Exception:
        return None
