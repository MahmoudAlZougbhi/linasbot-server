"""Tests for AI reply lifecycle + credit/delivery guarantee."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ai_reply_credit_gate import capture_after_reply_persisted, release_on_ai_failure, reserve_before_ai
from services.ai_reply_delivery import classify_send_result, record_delivery_outcome
from services.ai_reply_lifecycle import (
    begin_turn,
    find_pending_delivery_turn,
    get_turn,
    lifecycle_invariants,
    persist_generated_reply,
    put_turn,
)
from services.credit_ledger_service import CreditLedgerService
from services.entitlements_service import EntitlementsStore


@pytest.fixture()
def ledger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CreditLedgerService:
    store = EntitlementsStore(root=tmp_path / "ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", store)
    store.set_plan(tenant_id="t1", plan_id="starter", status="active", source="admin")
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    return ledger


@pytest.fixture()
def turn_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    turns = tmp_path / "ai_reply_turns"
    turns.mkdir(parents=True)
    import services.ai_reply_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "_store_dir", lambda: turns)


def test_capture_once_not_on_delivery_failure(ledger_env: CreditLedgerService, turn_store: None) -> None:
    ledger_env.ensure_period_grant("t1")
    before = ledger_env.get_balance("t1")
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-1", claim_key_basis="k1")
    rid = reserve_before_ai(turn)
    assert rid
    persist_generated_reply(turn.logical_reply_id, reply_text="Hello customer")
    first = capture_after_reply_persisted(turn.logical_reply_id)
    second = capture_after_reply_persisted(turn.logical_reply_id)
    assert first.get("duplicate") is not True
    assert second.get("duplicate") is True
    assert ledger_env.get_balance("t1") == before - 1

    record_delivery_outcome(turn.logical_reply_id, classify_send_result({"success": False, "error": "timeout"}))
    updated = get_turn(turn.logical_reply_id)
    assert updated is not None
    assert updated.state == "OUTBOUND_RETRY"
    assert updated.credit_captured is True
    assert ledger_env.get_balance("t1") == before - 1


def test_release_on_ai_failure_no_capture(ledger_env: CreditLedgerService, turn_store: None) -> None:
    ledger_env.ensure_period_grant("t1")
    before = ledger_env.get_balance("t1")
    turn = begin_turn(tenant_id="t1", channel="facebook", external_inbound_id="mid-2")
    rid = reserve_before_ai(turn)
    release_on_ai_failure(turn.logical_reply_id)
    assert ledger_env.get_balance("t1") == before
    assert ledger_env.get_reserved("t1") == 0
    rec = get_turn(turn.logical_reply_id)
    assert rec is not None
    assert rec.credit_captured is False


def test_pending_delivery_blocks_duplicate_generation(turn_store: None) -> None:
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-3", claim_key_basis="basis-3")
    turn.generated_reply = "Saved reply"
    turn.state = "OUTBOUND_RETRY"
    turn.credit_captured = True
    put_turn(turn)
    pending = find_pending_delivery_turn(claim_key_basis="basis-3")
    assert pending is not None
    assert pending.generated_reply == "Saved reply"


def test_lifecycle_invariants_zero_dup_capture(turn_store: None) -> None:
    inv = lifecycle_invariants([])
    assert inv["DUPLICATE_CREDIT_CAPTURES"] == 0
    assert inv["AI_GENERATED_WITHOUT_SAVED_REPLY"] == 0


def test_classify_send_result_permanent_block() -> None:
    out = classify_send_result({"success": False, "error": "OAuth permission blocked"})
    assert out["permanent_block"] is True
    assert out["retryable"] is False
