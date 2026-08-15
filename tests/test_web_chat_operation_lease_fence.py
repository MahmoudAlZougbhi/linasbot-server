"""Real-PG lease generation fencing fault matrix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
from services.web_chat.operation import (
    abandon_operation_lease,
    advance_operation,
    begin_operation,
    build_turn_payload,
    ensure_operation_credit_reserved,
    operation_session,
    refresh_operation_lease,
)
from services.web_chat.operation_fence import fenced_failure_release
from services.web_chat.operation_fsm import OperationFsmError, OperationState, stable_operation_key
from services.web_chat.pg_models import WebChatOperationRow
from services.web_chat.processor import WebChatError, _generate_reply_text, process_web_chat_message
from services.web_chat.session_authority import verified_session_snapshot
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.web_chat_acceptance_billing import assert_acceptance_ledger_equation, fetch_pg_ledger_snapshot
from tests.web_chat_acceptance_support import patch_acceptance_eligibility, patch_web_chat_store


def _expire_operation_lease(*, tenant_id: str, operation_key: str) -> None:
    with operation_session() as db:
        row = db.scalars(
            select(WebChatOperationRow).where(
                WebChatOperationRow.tenant_id == tenant_id,
                WebChatOperationRow.operation_key == operation_key,
            )
        ).first()
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
        db.commit()


def _operation_snapshot(*, tenant_id: str, operation_key: str) -> dict[str, object]:
    with operation_session() as db:
        row = db.scalars(
            select(WebChatOperationRow).where(
                WebChatOperationRow.tenant_id == tenant_id,
                WebChatOperationRow.operation_key == operation_key,
            )
        ).first()
        assert row is not None
        return {
            "state": row.state,
            "lease_owner": row.lease_owner,
            "lease_generation": int(row.lease_generation or 1),
            "released": bool(row.released),
            "reservation_id": row.reservation_id,
            "lease_expires_at": row.lease_expires_at,
        }


def _reserved_runtime_pair(
    *,
    tenant_id: str,
    visitor_id: str,
    client_key: str,
    widget,
    bundle,
) -> tuple[object, WebChatCreditHandle, str]:
    operation_key = stable_operation_key(session_id=visitor_id, client_key=client_key)
    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    request_id = f"web:{visitor_id}:{operation_key}"
    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )
    ensure_operation_credit_reserved(runtime, credit)
    assert runtime.record is not None
    assert runtime.record.state == OperationState.RESERVED
    return runtime, credit, operation_key


def _runtime_at_state(
    *,
    tenant_id: str,
    visitor_id: str,
    client_key: str,
    widget,
    bundle,
    target_state: OperationState,
) -> tuple[object, str]:
    runtime, credit, operation_key = _reserved_runtime_pair(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key=client_key,
        widget=widget,
        bundle=bundle,
    )
    turn_result = {"reply_text": "fence late-state probe"}
    advance_operation(runtime, OperationState.REPLY_READY, result=turn_result)
    if target_state == OperationState.RESERVED:
        return runtime, operation_key
    advance_operation(runtime, OperationState.DURABLE_VISIBLE, result=turn_result)
    if target_state == OperationState.DURABLE_VISIBLE:
        return runtime, operation_key
    if target_state == OperationState.BILLING_PENDING:
        advance_operation(
            runtime,
            OperationState.BILLING_PENDING,
            result=turn_result,
            reservation_id=credit.reservation_id,
        )
        return runtime, operation_key
    if target_state == OperationState.CAPTURED:
        advance_operation(
            runtime,
            OperationState.CAPTURED,
            result=turn_result,
            reservation_id=credit.reservation_id,
        )
        return runtime, operation_key
    raise AssertionError(f"unsupported target state: {target_state}")


@pytest.mark.parametrize(
    "target_state",
    [
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        OperationState.BILLING_PENDING,
    ],
)
def test_active_lease_cannot_be_stolen_in_late_nonterminal_states(
    tmp_path,
    monkeypatch,
    acceptance_pg_ha_env,
    target_state: OperationState,
) -> None:
    """Active DURABLE_VISIBLE/CAPTURED/BILLING_PENDING leases must fence concurrent claimers."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id
    client_key = f"lease-fence-late-{target_state.value}"

    runtime_a, operation_key = _runtime_at_state(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key=client_key,
        widget=widget,
        bundle=bundle,
        target_state=target_state,
    )
    owner_a = runtime_a.lease_owner
    generation_a = runtime_a.lease_generation

    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    with pytest.raises(OperationFsmError) as exc:
        begin_operation(
            tenant_id=tenant_id,
            operation_key=operation_key,
            payload=payload,
            snapshot=snapshot,
        )
    assert exc.value.code == "operation_in_progress"

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == target_state.value
    assert row["lease_owner"] == owner_a
    assert row["lease_generation"] == generation_a


def test_expired_durable_visible_lease_is_reclaimable(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Expired late-state leases remain reclaimable for crash recovery."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id
    client_key = "lease-fence-late-expired"

    runtime_a, operation_key = _runtime_at_state(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key=client_key,
        widget=widget,
        bundle=bundle,
        target_state=OperationState.DURABLE_VISIBLE,
    )
    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)

    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    runtime_b = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    assert runtime_b.lease_owner != runtime_a.lease_owner
    assert runtime_b.lease_generation == runtime_a.lease_generation + 1
    assert runtime_b.record is not None
    assert runtime_b.record.state == OperationState.DURABLE_VISIBLE


def test_stale_worker_abandon_does_not_touch_successor_lease(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Stale runtime A cannot expire B's lease via abandon_operation_lease after reclaim."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id

    runtime_a, _credit_a, operation_key = _reserved_runtime_pair(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key="lease-fence-stale-abandon",
        widget=widget,
        bundle=bundle,
    )
    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)

    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    runtime_b = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    before = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert before["lease_owner"] == runtime_b.lease_owner
    assert before["lease_generation"] == runtime_b.lease_generation
    assert before["lease_expires_at"] is not None
    assert before["lease_expires_at"] > datetime.now(UTC)

    abandon_operation_lease(runtime_a)

    after = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert after["lease_owner"] == runtime_b.lease_owner
    assert after["lease_generation"] == runtime_b.lease_generation
    assert after["lease_expires_at"] == before["lease_expires_at"]


def test_stale_worker_reserved_reclaim_blocks_release_and_external_effects(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """A exceeds lease during RESERVED; B reclaims; stale A cannot release or write RELEASED."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id

    runtime_a, credit_a, operation_key = _reserved_runtime_pair(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key="lease-fence-stale-reserved",
        widget=widget,
        bundle=bundle,
    )
    stale_owner = runtime_a.lease_owner
    stale_generation = runtime_a.lease_generation
    reservation_id = runtime_a.record.reservation_id
    assert reservation_id

    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)

    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    runtime_b = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    assert runtime_b.lease_owner != stale_owner
    assert runtime_b.lease_generation == stale_generation + 1
    assert runtime_b.record is not None
    assert runtime_b.record.state == OperationState.RESERVED
    assert runtime_b.record.reservation_id == reservation_id

    assert fenced_failure_release(runtime_a, credit_a) is False

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == OperationState.RESERVED.value
    assert row["lease_owner"] == runtime_b.lease_owner
    assert row["lease_generation"] == runtime_b.lease_generation
    assert row["released"] is False

    ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert ledger.reserved == 1
    assert ledger.ops.get("release", 0) == 0

    with pytest.raises(OperationFsmError) as stale_advance:
        advance_operation(runtime_a, OperationState.RELEASED, released=True)
    assert stale_advance.value.code == "lease_fence_stale"

    with pytest.raises(OperationFsmError) as stale_refresh:
        refresh_operation_lease(runtime_a)
    assert stale_refresh.value.code == "lease_fence_stale"

    credit_b = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        request_id=credit_a.request_id,
        operation_state=OperationState.RESERVED,
    )
    credit_b.state = CreditFsmState.RESERVED
    assert fenced_failure_release(runtime_b, credit_b) is True

    row_after_b = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row_after_b["state"] == OperationState.RELEASED.value
    assert row_after_b["lease_owner"] == runtime_b.lease_owner

    final_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        final_ledger,
        start_total=start_total,
        expected_available=start_total,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "release": 1, "reserve": 1},
    )


@pytest.mark.asyncio
async def test_processor_ai_failure_path_fenced_after_reserved_reclaim(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Stale worker A hitting processor _generate_reply_text failure must not release after B reclaims."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id

    runtime_a, credit_a, operation_key = _reserved_runtime_pair(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        client_key="lease-fence-processor-ai-fail",
        widget=widget,
        bundle=bundle,
    )
    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)

    snapshot = verified_session_snapshot(
        widget=widget,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    payload = build_turn_payload(session_id=visitor_id, content="fence probe")
    runtime_b = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    assert runtime_b.lease_generation == runtime_a.lease_generation + 1

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=RuntimeError("ai down")),
    )

    with pytest.raises(WebChatError) as exc:
        await _generate_reply_text(
            tid=tenant_id,
            text="hello",
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            widget=widget,
            visitor_id=visitor_id,
            user_id=f"web:{visitor_id}",
            word_notice=None,
            reply_precheck=None,
            credit=credit_a,
            runtime=runtime_a,
        )
    assert exc.value.code == "ai_failed"

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == OperationState.RESERVED.value
    assert row["lease_owner"] == runtime_b.lease_owner
    assert row["lease_generation"] == runtime_b.lease_generation

    ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert ledger.reserved == 1
    assert ledger.ops.get("release", 0) == 0
    assert_acceptance_ledger_equation(
        ledger,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )


@pytest.mark.asyncio
async def test_end_to_end_stale_ai_failure_after_reclaim_via_process_message(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Full processor path: reserve, expire, reclaim, then stale AI failure leaves B's lease intact."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id
    client_key = "lease-fence-e2e-ai-fail"
    operation_key = stable_operation_key(session_id=visitor_id, client_key=client_key)

    reserve_gate = {"done": False}

    async def reserve_then_fail(*_args, **_kwargs):
        if not reserve_gate["done"]:
            reserve_gate["done"] = True
            _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)
            snapshot = verified_session_snapshot(
                widget=widget,
                session_id=visitor_id,
                authority_hash=bundle.authority_hash,
            )
            payload = build_turn_payload(session_id=visitor_id, content="hello")
            begin_operation(
                tenant_id=tenant_id,
                operation_key=operation_key,
                payload=payload,
                snapshot=snapshot,
            )
        raise RuntimeError("ai down")

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=reserve_then_fail),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="hello",
            store=store,
            idempotency_key=client_key,
        )
    assert exc.value.code == "ai_failed"

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == OperationState.RESERVED.value
    assert row["lease_generation"] >= 2

    ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert ledger.reserved == 1
    assert ledger.ops.get("release", 0) == 0
    assert_acceptance_ledger_equation(
        ledger,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )
