"""Concurrency acceptance: 50 same-key calls must produce exactly one side-effect."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from services.web_chat.followup_delivery import deliver_web_followup_message
from services.web_chat.operation import (
    advance_operation,
    begin_operation,
    build_followup_payload,
    operation_session,
)
from services.web_chat.operation_fsm import OperationFsmError, OperationState, stable_operation_key
from services.web_chat.persistence import PersistOutcome, PersistResult
from services.web_chat.pg_models import WebChatOperationRow
from services.web_chat.processor import WebChatError, compose_web_user_id, process_web_chat_message
from services.web_chat.session_authority import issue_session_authority, verified_session_snapshot
from services.web_chat.store_pg import WebChatPgStore
from tests.web_chat_acceptance_billing import (
    assert_acceptance_ledger_equation,
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_web_chat_store,
    seed_acceptance_widget,
)
from tests.web_chat_runtime_support import (
    count_messages_by_role,
    fetch_ha_side_effect_counts,
    run_threaded_barrier_async,
)

_CONCURRENT_WORKERS = 50
_BARRIER_REPEAT_RUNS = 30


async def _deliver_followup_with_retry(
    *,
    tenant_id: str,
    visitor_id: str,
    user_id: str,
    conversation_id: str,
    reply_text: str,
    idem: str,
    widget_key: str,
    authority_hash: str,
    store: WebChatPgStore,
    reservation_id: str,
) -> str:
    for _ in range(100):
        try:
            result = await deliver_web_followup_message(
                tenant_id=tenant_id,
                visitor_id=visitor_id,
                user_id=user_id,
                conversation_id=conversation_id,
                reply_text=reply_text,
                idempotency_key=idem,
                widget_key=widget_key,
                authority_hash=authority_hash,
                store=store,
                reservation_id=reservation_id,
            )
            return result.status
        except OperationFsmError as exc:
            if exc.code not in {"operation_in_progress", "lease_fence_stale"}:
                raise
            await asyncio.sleep(0.02)
    raise AssertionError("concurrent follow-up delivery never settled")


def _assert_fifty_concurrent_followup_one_delivery(
    tmp_path,
    monkeypatch,
    acceptance_pg_ha_env,
    *,
    run_suffix: str,
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from tests.web_chat_acceptance_billing import truncate_billing_pg_tables

    truncate_billing_pg_tables(acceptance_pg_ha_env)
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    visitor_id = f"visitor-concurrent-50-{run_suffix}"
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    conversation_id = f"web:{tenant_id}:{visitor_id}"
    user_id = compose_web_user_id(visitor_id)
    idem = f"sfu:concurrent:acceptance:{run_suffix}"
    from tests.test_web_followup_web_delivery import _reserve_followup_credit

    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    persist_lock = threading.Lock()
    persist_calls = 0
    created_calls = 0

    async def counting_persist(**_kwargs):
        nonlocal persist_calls, created_calls
        with persist_lock:
            persist_calls += 1
            if created_calls == 0:
                created_calls += 1
                outcome = PersistOutcome.CREATED
            else:
                outcome = PersistOutcome.DUPLICATE
        return PersistResult(outcome=outcome, conversation_id=conversation_id)

    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", counting_persist)

    async def one_delivery() -> str:
        return await _deliver_followup_with_retry(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=user_id,
            conversation_id=conversation_id,
            reply_text="Concurrent follow-up",
            idem=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )

    outcomes = run_threaded_barrier_async(workers=_CONCURRENT_WORKERS, coro_factory=one_delivery)
    delivered = sum(1 for status in outcomes if status == "delivered")
    already = sum(1 for status in outcomes if status == "already_delivered")
    assert delivered + already == _CONCURRENT_WORKERS
    assert created_calls == 1
    assert persist_calls >= 1

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=visitor_id)
    assert counts.pending_outbox == 1
    assert counts.assistant_messages == 2
    assert counts.user_messages == 0
    assert counts.operations == 1

    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1
    assert session.pending_assistant[0].id == idem

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )


def test_fifty_concurrent_ha_idempotency_claims(web_chat_ha_db) -> None:
    """Supplementary: PostgreSQL claim primitive under thread contention."""
    from services.web_chat.ha_repository import WebChatHaRepository

    repo = WebChatHaRepository()
    with web_chat_ha_db() as db:
        repo.create_session(
            db,
            session_id="visitor-thread-50",
            tenant_id="biz",
            widget_key="wk-thread",
            authority_hash="hash",
            greeting="Hi",
        )
        db.commit()

    def claim_once() -> bool:
        with web_chat_ha_db() as db:
            ok = repo.claim_idempotency(
                db,
                tenant_id="biz",
                session_id="visitor-thread-50",
                idempotency_key="sfu:thread:50",
                message_id="sfu:thread:50",
            )
            db.commit()
            return ok

    with ThreadPoolExecutor(max_workers=_CONCURRENT_WORKERS) as pool:
        results = list(pool.map(lambda _: claim_once(), range(_CONCURRENT_WORKERS)))

    assert sum(1 for ok in results if ok) == 1
    assert sum(1 for ok in results if not ok) == 49


def test_fifty_concurrent_same_idempotency_key_one_delivery(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Mandatory: threaded barrier + independent DB sessions → one follow-up delivery."""
    _assert_fifty_concurrent_followup_one_delivery(tmp_path, monkeypatch, acceptance_pg_ha_env, run_suffix="1")


def test_fifty_concurrent_same_idempotency_key_barrier_repeated(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Barrier-controlled real PostgreSQL regression repeated to flush races."""
    for run_index in range(_BARRIER_REPEAT_RUNS):
        _assert_fifty_concurrent_followup_one_delivery(
            tmp_path,
            monkeypatch,
            acceptance_pg_ha_env,
            run_suffix=f"repeat-{run_index}",
        )


def test_reply_ready_expired_lease_reclaim_one_delivery(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Crash/reclaim: expired REPLY_READY lease resumes to exactly one visible delivery."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    visitor_id = "visitor-reply-ready-reclaim"
    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    conversation_id = f"web:{tenant_id}:{visitor_id}"
    user_id = compose_web_user_id(visitor_id)
    idem = "sfu:reply-ready-reclaim:1"
    from tests.test_web_followup_web_delivery import _reserve_followup_credit

    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)
    snapshot = verified_session_snapshot(
        tenant_id=tenant_id,
        widget_key=widget_key,
        session_id=visitor_id,
        authority_hash=bundle.authority_hash,
    )
    operation_key = stable_operation_key(session_id=visitor_id, client_key=idem)
    payload = build_followup_payload(visitor_id=visitor_id, reply_text="Reclaim follow-up", idempotency_key=idem)

    runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=snapshot,
    )
    advance_operation(runtime, OperationState.RESERVED, reservation_id=reservation_id)
    advance_operation(
        runtime, OperationState.REPLY_READY, result={"reply_text": "Reclaim follow-up", "idempotency_key": idem}
    )

    with operation_session() as db:
        row = db.scalars(
            select(WebChatOperationRow).where(
                WebChatOperationRow.tenant_id == tenant_id,
                WebChatOperationRow.operation_key == operation_key,
            )
        ).first()
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=30)
        db.commit()

    monkeypatch.setattr(
        "services.web_chat.followup_delivery.persist_web_chat_message",
        AsyncMock(
            return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id=conversation_id),
        ),
    )

    first = asyncio.run(
        _deliver_followup_with_retry(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=user_id,
            conversation_id=conversation_id,
            reply_text="Reclaim follow-up",
            idem=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )
    )
    second = asyncio.run(
        _deliver_followup_with_retry(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=user_id,
            conversation_id=conversation_id,
            reply_text="Reclaim follow-up",
            idem=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )
    )
    assert first == "delivered"
    assert second == "already_delivered"

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=visitor_id)
    assert counts.pending_outbox == 1
    assert counts.operations == 1


def test_same_key_followup_barrier_then_sequential_retry(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Barrier burst then sequential retries on real PG — one delivery, ledger unchanged."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    visitor_id = "visitor-followup-retry"
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    conversation_id = f"web:{tenant_id}:{visitor_id}"
    user_id = compose_web_user_id(visitor_id)
    idem = "sfu:barrier-retry:1"
    from tests.test_web_followup_web_delivery import _reserve_followup_credit

    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    monkeypatch.setattr(
        "services.web_chat.followup_delivery.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=conversation_id,
            )
        ),
    )

    async def one_delivery() -> str:
        for _ in range(100):
            try:
                result = await deliver_web_followup_message(
                    tenant_id=tenant_id,
                    visitor_id=visitor_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    reply_text="Retry-safe follow-up",
                    idempotency_key=idem,
                    widget_key=widget_key,
                    authority_hash=bundle.authority_hash,
                    store=store,
                    reservation_id=reservation_id,
                )
                return result.status
            except OperationFsmError as exc:
                if exc.code not in {"operation_in_progress", "lease_fence_stale"}:
                    raise
                await asyncio.sleep(0.02)
        raise AssertionError("follow-up barrier retry never settled")

    burst = run_threaded_barrier_async(workers=20, coro_factory=one_delivery)
    assert sum(1 for status in burst if status == "delivered") == 1
    assert sum(1 for status in burst if status == "already_delivered") == 19

    async def sequential_retries() -> list[str]:
        outcomes: list[str] = []
        for _ in range(10):
            outcomes.append(await one_delivery())
        return outcomes

    retries = asyncio.run(sequential_retries())
    assert all(status == "already_delivered" for status in retries)

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=visitor_id)
    assert counts.pending_outbox == 1
    assert counts.operations == 1

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )


def test_concurrent_same_client_key_one_operation(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Mandatory: threaded barrier on inbound turn → one PG reserve/capture chain."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)

    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor = store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    ai_lock = threading.Lock()
    ai_calls = 0

    async def gated_ai(*_args, **_kwargs):
        nonlocal ai_calls
        with ai_lock:
            ai_calls += 1
        return MagicMock(reply="One reply")

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=gated_ai),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{tenant_id}:{bundle.session_id}",
            )
        ),
    )

    async def run_turn() -> str:
        for _ in range(100):
            try:
                return await process_web_chat_message(
                    widget=widget,
                    visitor_session=visitor,
                    user_text="Concurrent hello",
                    store=store,
                    idempotency_key="client-key-50",
                )
            except WebChatError as exc:
                if exc.code not in {"operation_in_progress", "lease_fence_stale"}:
                    raise
                await asyncio.sleep(0.02)
        raise AssertionError("concurrent replay never became available")

    replies = run_threaded_barrier_async(workers=_CONCURRENT_WORKERS, coro_factory=run_turn)
    assert all(reply == "One reply" for reply in replies)
    assert ai_calls == 1

    refreshed = store.get_visitor(bundle.session_id)
    assert refreshed is not None
    user_msgs = [m for m in refreshed.messages if m.role == "user" and m.content == "Concurrent hello"]
    assert len(user_msgs) == 1

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=bundle.session_id)
    assert counts.user_messages == 1
    assert counts.assistant_messages == 2  # greeting + one turn reply
    assert counts.pending_outbox == 0
    assert counts.operations == 1
    assert count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="user") == 1

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert snapshot.ops.get("reserve", 0) == 1
    assert snapshot.ops.get("capture", 0) == 1
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )
