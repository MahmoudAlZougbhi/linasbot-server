"""unexplained_financial_delta == 0 for credit grant/reverse paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.billing.credit_ledger_service import CreditLedgerService
from services.billing.entitlements_service import EntitlementsStore


@pytest.fixture()
def ledger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CreditLedgerService:
    store = EntitlementsStore(root=tmp_path / "ents")
    monkeypatch.setattr("services.billing.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.billing.credit_ledger_service.entitlements_store", store)
    store.set_plan(tenant_id="fin", plan_id="starter", status="active", source="admin")
    return CreditLedgerService(root=tmp_path / "ledger")


def test_grant_reverse_unexplained_financial_delta_zero(ledger_env: CreditLedgerService) -> None:
    ledger = ledger_env
    before = ledger.get_balance("fin")
    ledger.grant_pack(tenant_id="fin", credits=500, request_id="txn-fin-1", source="apple")
    mid = ledger.get_balance("fin")
    ledger.reverse_pack(tenant_id="fin", request_id="txn-fin-1", credits=500)
    after = ledger.get_balance("fin")
    assert (mid - before) == 500
    assert (after - before) == 0
    # Duplicate reverse must not invent further delta
    ledger.reverse_pack(tenant_id="fin", request_id="txn-fin-1", credits=500)
    assert ledger.get_balance("fin") == after
