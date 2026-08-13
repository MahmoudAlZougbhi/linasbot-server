"""Tests for customer reply reconciliation worker (A/B/C/D classification + safeguards)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from services.ai_reply_credit_gate import capture_after_reply_persisted, reserve_before_ai
from services.ai_reply_delivery import classify_send_result, record_delivery_outcome
from services.ai_reply_lifecycle import begin_turn, get_turn, put_turn
from services.credit_ledger_service import CreditLedgerService
from services.customer_reply_reconcile_classify import (
    classify_event_turn,
    scan_reconcile_candidates,
    summarize_candidates,
)
from services.customer_reply_reconcile_worker import reconcile_customer_replies, reset_reconcile_metrics
from services.durable_event_claim import _file_claim_path
from services.entitlements_service import EntitlementsStore
from services.scale.inbound_event_store import (
    InboundEventRecord,
    get_inbound_event,
    put_inbound_event,
    stable_event_id,
)


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
def stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs = tmp_path / "logs"
    turns = logs / "ai_reply_turns"
    inbound = logs / "inbound_events"
    claims = logs / "durable_claims"
    turns.mkdir(parents=True)
    inbound.mkdir(parents=True)
    claims.mkdir(parents=True)

    import services.ai_reply_lifecycle as lifecycle
    import services.scale.inbound_event_store as inbound_store

    monkeypatch.setattr(lifecycle, "LOGS_DIR", logs)
    monkeypatch.setattr(lifecycle, "ensure_dirs", lambda: None)
    monkeypatch.setattr(inbound_store, "LOGS_DIR", logs)
    monkeypatch.setattr(inbound_store, "ensure_dirs", lambda: None)

    import storage.persistent_storage as ps

    monkeypatch.setattr(ps, "LOGS_DIR", logs)

    import services.durable_event_claim as claims_mod

    monkeypatch.setattr(claims_mod, "LOGS_DIR", logs)
    monkeypatch.setattr(claims_mod, "ensure_dirs", lambda: None)
    return logs


def _seed_inbound(
    *,
    message_id: str,
    state: str = "processing",
    attempts: int = 0,
    outbound_status: str | None = None,
    age_seconds: float = 120.0,
) -> InboundEventRecord:
    claim_key = f"t1:instagram:{message_id}"
    event_id = stable_event_id("meta_dm", claim_key)
    now = time.time()
    rec = InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="t1",
        claim_namespace="meta_social_dm_global",
        claim_key=claim_key,
        state=state,  # type: ignore[arg-type]
        created_at=now - age_seconds,
        updated_at=now - age_seconds,
        payload={"message_id": message_id, "channel": "instagram", "text": "hello"},
        conversation_key="t1:instagram:psid",
        attempts=attempts,
        outbound_status=outbound_status,
    )
    return put_inbound_event(rec)


def _write_stale_claim(key_basis: str, *, age_seconds: float = 300.0) -> None:
    path = _file_claim_path("ai_turn_claims", key_basis)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "namespace": "ai_turn_claims",
        "key_prefix": key_basis[:200],
        "created_at": time.time() - age_seconds,
        "status": "claimed",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_worker_crash_before_ai_requeues_without_duplicate_charge(
    stores: Path,
    ledger_env: CreditLedgerService,
) -> None:
    ledger_env.ensure_period_grant("t1")
    before = ledger_env.get_balance("t1")
    event = _seed_inbound(message_id="mid-crash-before-ai", state="processing")
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-crash-before-ai",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-before-ai",
    )
    turn.state = "AI_PROCESSING"
    reserve_before_ai(turn)
    put_turn(turn)
    _write_stale_claim("basis-before-ai")

    reset_reconcile_metrics()
    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0, claim_ttl_seconds=60.0)
    actions = result.get("actions") or []
    assert any(a.get("action") == "requeue_ai" for a in actions)
    assert ledger_env.get_balance("t1") == before
    refreshed = get_inbound_event(event.event_id)
    assert refreshed is not None
    assert refreshed.state in {"accepted", "queued"}
    assert result["metrics"]["stale_claims_count"] >= 1


@pytest.mark.asyncio
async def test_worker_crash_after_ai_retries_delivery_only(
    stores: Path,
    ledger_env: CreditLedgerService,
) -> None:
    ledger_env.ensure_period_grant("t1")
    event = _seed_inbound(message_id="mid-crash-after-ai", state="failed")
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-crash-after-ai",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-after-ai",
    )
    reserve_before_ai(turn)
    turn = get_turn(turn.logical_reply_id)
    assert turn is not None
    turn.generated_reply = "Saved after outage"
    turn.state = "OUTBOUND_RETRY"
    put_turn(turn)
    capture_after_reply_persisted(turn.logical_reply_id)
    after_capture = ledger_env.get_balance("t1")

    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0)
    actions = result.get("actions") or []
    assert any(a.get("action") == "retry_delivery" for a in actions)
    assert ledger_env.get_balance("t1") == after_capture
    updated = get_turn(turn.logical_reply_id)
    assert updated is not None
    assert updated.state == "DELIVERY_RETRY_WITHOUT_REGENERATION"


@pytest.mark.asyncio
async def test_duplicate_claim_after_restart_classified_as_requeue_ai(stores: Path) -> None:
    event = _seed_inbound(message_id="mid-dup-claim", state="processing")
    begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-dup-claim",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-dup",
    )
    _write_stale_claim("basis-dup")

    candidate = scan_reconcile_candidates(older_than_seconds=0.0, claim_ttl_seconds=60.0)[0]
    assert candidate.classification == "A"
    assert candidate.action == "requeue_ai"
    assert candidate.stale_claim is True


@pytest.mark.asyncio
async def test_stale_claim_recovery_releases_and_requeues(stores: Path) -> None:
    event = _seed_inbound(message_id="mid-stale-claim", state="processing")
    begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-stale-claim",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-stale",
    )
    _write_stale_claim("basis-stale", age_seconds=600.0)

    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0, claim_ttl_seconds=120.0)
    action = next(a for a in result["actions"] if a["event_id"] == event.event_id)
    assert action["action"] == "requeue_ai"
    assert action.get("released_stale_claim") is True


@pytest.mark.asyncio
async def test_replay_after_openai_outage(stores: Path, ledger_env: CreditLedgerService) -> None:
    ledger_env.ensure_period_grant("t1")
    event = _seed_inbound(message_id="mid-openai-outage", state="failed", attempts=1)
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-openai-outage",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-openai",
    )
    turn.state = "AI_RETRY_REQUIRED"
    put_turn(turn)

    candidate = classify_event_turn(event, get_turn(turn.logical_reply_id))
    assert candidate.classification == "A"
    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0)
    assert any(a.get("action") == "requeue_ai" for a in result["actions"])


@pytest.mark.asyncio
async def test_replay_after_meta_outage_delivery_only(stores: Path, ledger_env: CreditLedgerService) -> None:
    ledger_env.ensure_period_grant("t1")
    event = _seed_inbound(message_id="mid-meta-outage", state="failed")
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-meta-outage",
        inbound_event_id=event.event_id,
        claim_key_basis="basis-meta",
    )
    reserve_before_ai(turn)
    turn = get_turn(turn.logical_reply_id)
    assert turn is not None
    turn.generated_reply = "Reply ready"
    turn.state = "CREDIT_CAPTURED_ONCE"
    put_turn(turn)
    capture_after_reply_persisted(turn.logical_reply_id)
    after_capture = ledger_env.get_balance("t1")
    record_delivery_outcome(
        turn.logical_reply_id,
        classify_send_result({"success": False, "error": "Meta timeout"}),
    )

    candidate = classify_event_turn(event, get_turn(turn.logical_reply_id))
    assert candidate.classification == "B"
    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0)
    assert any(a.get("action") == "retry_delivery" for a in result["actions"])
    assert ledger_env.get_balance("t1") == after_capture


@pytest.mark.asyncio
async def test_delivered_event_is_noop(stores: Path) -> None:
    event = _seed_inbound(
        message_id="mid-delivered",
        state="completed",
        outbound_status="sent",
    )
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-delivered",
        inbound_event_id=event.event_id,
    )
    turn.generated_reply = "Done"
    turn.state = "DELIVERED"
    turn.delivery_evidence = {"success": True}
    put_turn(turn)

    candidate = classify_event_turn(event, get_turn(turn.logical_reply_id))
    assert candidate.classification == "C"
    assert candidate.action in {"none", "complete_inbound"}


@pytest.mark.asyncio
async def test_ambiguous_credit_without_reply_marked_for_investigation(stores: Path) -> None:
    event = _seed_inbound(message_id="mid-ambiguous", state="processing")
    turn = begin_turn(
        tenant_id="t1",
        channel="instagram",
        external_inbound_id="mid-ambiguous",
        inbound_event_id=event.event_id,
    )
    turn.credit_captured = True
    turn.state = "CREDIT_CAPTURED_ONCE"
    put_turn(turn)

    candidate = classify_event_turn(event, get_turn(turn.logical_reply_id))
    assert candidate.classification == "D"
    result = await reconcile_customer_replies(dry_run=False, older_than_seconds=0.0)
    assert any(a.get("action") == "mark_ambiguous" for a in result["actions"])


def test_dry_run_report_format(stores: Path) -> None:
    _seed_inbound(message_id="mid-dry-run", state="processing")
    candidates = scan_reconcile_candidates(older_than_seconds=0.0)
    summary = summarize_candidates(candidates)
    assert "stuck_events_count" in summary
    assert "by_classification" in summary
    assert summary["examined"] >= 1
