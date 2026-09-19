"""PostgreSQL message-ledger helpers for Website Chat acceptance tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text

_BILLING_PG_TABLES: tuple[str, ...] = (
    "credit_ledger_entries",
    "credit_balances",
    "entitlement_processed_events",
    "tenant_entitlements",
)


def truncate_billing_pg_tables(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE credit_ledger_entries, credit_balances, "
                "entitlement_processed_events, tenant_entitlements, "
                "customer_ai_message_reservations, customer_ai_message_lots "
                "RESTART IDENTITY CASCADE"
            )
        )


def wire_pg_billing_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.billing import entitlements_service as es
    from services.billing.entitlements_service import EntitlementsStore
    from services.billing.membership import web_gate as wg

    ent = EntitlementsStore()
    monkeypatch.setattr(es, "entitlements_store", ent)
    monkeypatch.setattr(wg, "entitlements_store", ent)
    monkeypatch.setattr("services.billing.credit_ledger_service.entitlements_store", ent)
    monkeypatch.setattr("services.billing.credit_ledger_pg_ops.entitlements_store", ent)


def seed_acceptance_credit_ledger(*, tenant_id: str = "biz", plan_id: str = "starter") -> int:
    from services.billing.credit_ledger_service import credit_ledger_service
    from services.billing.entitlements_service import entitlements_store
    from services.billing.membership.message_ledger import remaining_messages
    from services.billing.membership.period_grants import ensure_included_grant

    entitlements_store.set_plan(tenant_id=tenant_id, plan_id=plan_id, status="active", source="admin")
    credit_ledger_service.ensure_period_grant(tenant_id)
    ensure_included_grant(tenant_id)
    return int(remaining_messages(tenant_id))


@dataclass(frozen=True)
class PgLedgerSnapshot:
    available: int
    reserved: int
    ops: dict[str, int]

    @property
    def spendable_total(self) -> int:
        return self.available + self.reserved


def fetch_pg_ledger_snapshot(url: str, tenant_id: str) -> PgLedgerSnapshot:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        lot_sum = conn.execute(
            text("SELECT COALESCE(SUM(remaining), 0) FROM customer_ai_message_lots WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar()
        reserved = conn.execute(
            text(
                "SELECT COALESCE(SUM(units), 0) FROM customer_ai_message_reservations "
                "WHERE tenant_id = :tid AND status = 'reserved'"
            ),
            {"tid": tenant_id},
        ).scalar()
        statuses = conn.execute(
            text(
                "SELECT status, COUNT(*) AS n FROM customer_ai_message_reservations "
                "WHERE tenant_id = :tid GROUP BY status"
            ),
            {"tid": tenant_id},
        ).fetchall()
        included = conn.execute(
            text("SELECT COUNT(*) FROM customer_ai_message_lots WHERE tenant_id = :tid AND kind = 'included'"),
            {"tid": tenant_id},
        ).scalar()
    reserved_n = int(reserved or 0)
    available = max(0, int(lot_sum or 0) - reserved_n)
    counts = {str(status): int(count) for status, count in statuses}
    ops: dict[str, int] = {}
    if int(included or 0):
        ops["grant_included"] = int(included)
    reserved_rows = sum(counts.values())
    if reserved_rows:
        ops["reserve"] = reserved_rows
    if counts.get("settled"):
        ops["capture"] = counts["settled"]
    if counts.get("released"):
        ops["release"] = counts["released"]
    return PgLedgerSnapshot(available=available, reserved=reserved_n, ops=ops)


def assert_acceptance_ledger_equation(
    snapshot: PgLedgerSnapshot,
    *,
    start_total: int,
    expected_available: int,
    expected_reserved: int,
    expected_ops: dict[str, int] | None = None,
    captured: int = 0,
) -> None:
    """Conservation: available + reserved + captured == start_total."""
    assert snapshot.available == expected_available, snapshot
    assert snapshot.reserved == expected_reserved, snapshot
    assert snapshot.spendable_total + captured == start_total, (
        f"ledger conservation failed: {snapshot.spendable_total} + {captured} != {start_total}"
    )
    if expected_ops is not None:
        assert snapshot.ops == expected_ops, snapshot


def assert_pg_reservation_terminal(
    url: str,
    tenant_id: str,
    reservation_id: str,
    *,
    terminal: str,
) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    mapped = {"capture": "settled", "release": "released"}
    wanted = mapped.get(terminal, terminal)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT status FROM customer_ai_message_reservations "
                "WHERE tenant_id = :tid AND (reservation_id = :rid OR operation_id = :rid)"
            ),
            {"tid": tenant_id, "rid": reservation_id},
        ).fetchall()
    statuses = {str(row[0]) for row in rows}
    assert wanted in statuses, f"expected terminal {wanted!r}, got {statuses}"
