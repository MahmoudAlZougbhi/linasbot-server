"""Postgres credit ledger + entitlements via LINAS_BILLING_BACKEND=postgres."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.credit_ledger_service import CreditLedgerService  # noqa: E402
from services.entitlements_service import (  # noqa: E402
    EntitlementsStore,
    apply_store_notification,
)


@pytest.fixture()
def pg_billing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'credit_ent.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    store = EntitlementsStore(root=tmp_path / "ents_unused")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", store)
    yield tmp_path
    reset_engine_for_tests()


def test_pg_credit_reserve_capture_idempotent(pg_billing: Path) -> None:
    ledger = CreditLedgerService(root=pg_billing / "file_unused")
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(
        tenant_id="t1", plan_id="starter", status="active", source="admin"
    )
    ledger.ensure_period_grant("t1")
    rid = ledger.reserve(
        tenant_id="t1",
        user_id="u1",
        credits=10,
        operation_type="ai",
        request_id="job-1",
    )
    assert ledger.get_reserved("t1") == 10
    first = ledger.capture(
        tenant_id="t1", reservation_id=rid, provider_cost_usd=0.01, model_provider="x"
    )
    second = ledger.capture(
        tenant_id="t1", reservation_id=rid, provider_cost_usd=0.01, model_provider="x"
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert ledger.get_reserved("t1") == 0


def test_pg_grant_pack_idempotent_and_entitlement(pg_billing: Path) -> None:
    ledger = CreditLedgerService(root=pg_billing / "file_unused")
    from services.entitlements_service import entitlements_store

    entitlements_store.set_plan(
        tenant_id="t2", plan_id="starter", status="active", source="admin"
    )
    a = ledger.grant_pack(tenant_id="t2", credits=100, request_id="txn-1", source="apple")
    b = ledger.grant_pack(tenant_id="t2", credits=100, request_id="txn-1", source="apple")
    assert a["duplicate"] is False
    assert b["duplicate"] is True
    ent = entitlements_store.get("t2")
    assert ent.extra_credits >= 100


def test_pg_entitlement_notification_idempotent(pg_billing: Path) -> None:
    r1 = apply_store_notification(
        tenant_id="t3",
        plan_id="growth",
        status="active",
        source="apple",
        original_transaction_id="ot1",
        idempotency_key="evt-1",
    )
    r2 = apply_store_notification(
        tenant_id="t3",
        plan_id="growth",
        status="active",
        source="apple",
        original_transaction_id="ot1",
        idempotency_key="evt-1",
    )
    assert r1["duplicate"] is False
    assert r2["duplicate"] is True
