"""Postgres persistence for internal expense events."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from services.membership.expense_journal import ExpenseEvent


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_expense_events'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_expense_events')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_record(session: Any, event: ExpenseEvent) -> ExpenseEvent:
    existing = session.execute(
        text("SELECT event_id FROM customer_ai_expense_events WHERE event_id = :eid"),
        {"eid": event.event_id},
    ).first()
    if existing:
        return event
    session.execute(
        text(
            "INSERT INTO customer_ai_expense_events "
            "(event_id, tenant_id, category, feature, provider, model, amount_usd, quantity, "
            "status, environment, operation_id, parent_event_id) "
            "VALUES (:event_id, :tenant_id, :category, :feature, :provider, :model, :amount_usd, "
            ":quantity, :status, :environment, :operation_id, :parent_event_id)"
        ),
        {
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "category": event.category,
            "feature": event.feature,
            "provider": event.provider,
            "model": event.model,
            "amount_usd": None if event.amount_usd is None else str(event.amount_usd),
            "quantity": str(event.quantity),
            "status": event.status,
            "environment": event.environment,
            "operation_id": event.operation_id,
            "parent_event_id": event.parent_event_id,
        },
    )
    return event


def pg_list(
    session: Any,
    *,
    tenant_id: str | None,
    environment: str | None,
) -> list[ExpenseEvent]:
    sql = (
        "SELECT event_id, tenant_id, category, feature, provider, model, amount_usd, quantity, "
        "status, environment, operation_id, parent_event_id, created_at "
        "FROM customer_ai_expense_events WHERE 1=1"
    )
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    if environment:
        sql += " AND environment = :env"
        params["env"] = environment
    rows = session.execute(text(sql), params).mappings().all()
    events: list[ExpenseEvent] = []
    for row in rows:
        amount = row["amount_usd"]
        events.append(
            ExpenseEvent(
                event_id=row["event_id"],
                tenant_id=row["tenant_id"],
                category=row["category"],
                feature=row["feature"],
                provider=row["provider"],
                model=row["model"] or "",
                amount_usd=None if amount is None else Decimal(str(amount)),
                quantity=Decimal(str(row["quantity"] or 1)),
                status=row["status"],
                environment=row["environment"],
                operation_id=row["operation_id"] or "",
                parent_event_id=row["parent_event_id"] or "",
                created_at=str(row["created_at"] or ""),
            )
        )
    return events
