"""Atomic Apple credit grant when billing backend is Postgres."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.apple_billing import AppleCreditGrantRow  # noqa: E402
from db.models.credit_entitlements import CreditLedgerEntryRow  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.apple_credit_grant_ops import grant_consumable_credits  # noqa: E402
from services.entitlements_service import EntitlementsStore  # noqa: E402


@pytest.fixture()
def apple_pg_billing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_atomic.db'}"
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


def test_grant_consumable_atomic_idempotent(apple_pg_billing: Path) -> None:
    first = grant_consumable_credits(
        tenant_id="tenant_atomic",
        product_id="com.linasai.credits.2500",
        transaction_id="txn_atomic_1",
    )
    second = grant_consumable_credits(
        tenant_id="tenant_atomic",
        product_id="com.linasai.credits.2500",
        transaction_id="txn_atomic_1",
    )
    assert first["duplicate"] is False
    assert first["credits"] == 2500
    assert second["duplicate"] is True

    with whatsapp_session() as session:
        row = session.get(AppleCreditGrantRow, "txn_atomic_1")
        assert row is not None
        assert row.status == "granted"
        grants = list(
            session.scalars(
                select(CreditLedgerEntryRow).where(
                    CreditLedgerEntryRow.tenant_id == "tenant_atomic",
                    CreditLedgerEntryRow.op == "grant_pack",
                    CreditLedgerEntryRow.request_id == "txn_atomic_1",
                )
            )
        )
    assert len(grants) == 1
