"""Internal provider-expense journal. Never a customer wallet or message debit."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal


def expense_environment(raw: str | None = None) -> str:
    value = (raw if raw is not None else os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    if value in {"production", "prod"}:
        return "prod"
    if value in {"staging", "stage"}:
        return "staging"
    if value:
        return value
    return "test"

ExpenseCategory = Literal[
    "llm_generation",
    "embedding",
    "rerank",
    "translation",
    "stt",
    "visual",
    "metadata",
    "other",
    "shared",
]

ExpenseStatus = Literal["known", "pending", "unpriced", "estimated", "adjusted"]

_LOCK = threading.Lock()
_EVENTS: list["ExpenseEvent"] = []


@dataclass
class ExpenseEvent:
    event_id: str
    tenant_id: str
    category: ExpenseCategory
    feature: str
    provider: str
    model: str
    amount_usd: Decimal | None
    quantity: Decimal
    status: ExpenseStatus
    environment: str = "test"
    operation_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    parent_event_id: str = ""


def reset_expenses_for_tests() -> None:
    with _LOCK:
        _EVENTS.clear()


def record_expense(
    *,
    event_id: str,
    tenant_id: str,
    category: ExpenseCategory,
    feature: str,
    provider: str,
    model: str,
    amount_usd: str | float | Decimal | None,
    quantity: str | float | Decimal = 1,
    status: ExpenseStatus = "known",
    environment: str | None = None,
    operation_id: str = "",
    parent_event_id: str = "",
) -> ExpenseEvent:
    amount = None if amount_usd is None else Decimal(str(amount_usd))
    event = ExpenseEvent(
        event_id=event_id,
        tenant_id=tenant_id.strip(),
        category=category,
        feature=feature,
        provider=provider,
        model=model,
        amount_usd=amount,
        quantity=Decimal(str(quantity)),
        status=status,
        environment=expense_environment(environment),
        operation_id=operation_id,
        parent_event_id=parent_event_id,
    )
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.expense_journal_pg import pg_record, table_ready

            if table_ready(session):
                pg_record(session, event)
    with _LOCK:
        existing = next((item for item in _EVENTS if item.event_id == event_id), None)
        if existing is not None:
            return existing
        _EVENTS.append(event)
        return event


def list_events(
    *,
    tenant_id: str | None = None,
    environment: str | None = None,
    category: str | None = None,
    feature: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[ExpenseEvent]:
    from services.membership.pg_store import optional_message_session

    sql_rows: list[ExpenseEvent] = []
    with optional_message_session() as session:
        if session is not None:
            from services.membership.expense_journal_pg import pg_list, table_ready

            if table_ready(session):
                sql_rows = pg_list(session, tenant_id=tenant_id, environment=environment)
    with _LOCK:
        mem_rows = list(_EVENTS)
    seen = {item.event_id for item in sql_rows}
    rows = list(sql_rows)
    for item in mem_rows:
        if item.event_id in seen:
            continue
        if tenant_id and item.tenant_id != tenant_id:
            continue
        if environment and item.environment != environment:
            continue
        rows.append(item)
        seen.add(item.event_id)
    if category:
        rows = [item for item in rows if item.category == category]
    if feature:
        rows = [item for item in rows if item.feature == feature]
    if provider:
        rows = [item for item in rows if item.provider == provider]
    if model:
        rows = [item for item in rows if item.model == model]
    if since:
        rows = [item for item in rows if item.created_at >= since]
    if until:
        rows = [item for item in rows if item.created_at <= until]
    return rows


def known_total(events: list[ExpenseEvent]) -> Decimal:
    return sum((item.amount_usd or Decimal("0") for item in events if item.status == "known"), Decimal("0"))


def event_dict(event: ExpenseEvent) -> dict[str, Any]:
    return {
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
        "created_at": event.created_at,
        "parent_event_id": event.parent_event_id,
    }
