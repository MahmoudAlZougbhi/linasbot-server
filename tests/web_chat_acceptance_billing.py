"""PostgreSQL credit-ledger helpers for Website Chat acceptance tests."""

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
                "entitlement_processed_events, tenant_entitlements "
                "RESTART IDENTITY CASCADE"
            )
        )


def wire_pg_billing_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import web_gate as wg

    ent = EntitlementsStore()
    monkeypatch.setattr(es, "entitlements_store", ent)
    monkeypatch.setattr(wg, "entitlements_store", ent)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", ent)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", ent)


def seed_acceptance_credit_ledger(*, tenant_id: str = "biz", plan_id: str = "starter") -> int:
    from services.credit_ledger_service import credit_ledger_service
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(tenant_id=tenant_id, plan_id=plan_id, status="active", source="admin")
    credit_ledger_service.ensure_period_grant(tenant_id)
    return int(credit_ledger_service.get_balance(tenant_id))


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
        balance = conn.execute(
            text("SELECT available, reserved FROM credit_balances WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).fetchone()
        rows = conn.execute(
            text("SELECT op, COUNT(*) AS n FROM credit_ledger_entries WHERE tenant_id = :tid GROUP BY op ORDER BY op"),
            {"tid": tenant_id},
        ).fetchall()
    available = int(balance[0]) if balance is not None else 0
    reserved = int(balance[1]) if balance is not None else 0
    ops = {str(op): int(count) for op, count in rows}
    return PgLedgerSnapshot(available=available, reserved=reserved, ops=ops)


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
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT op FROM credit_ledger_entries "
                "WHERE tenant_id = :tid AND request_id = :rid AND op IN ('capture', 'release')"
            ),
            {"tid": tenant_id, "rid": reservation_id},
        ).fetchall()
    terminals = {str(row[0]) for row in rows}
    assert terminal in terminals, f"expected terminal {terminal!r}, got {terminals}"
