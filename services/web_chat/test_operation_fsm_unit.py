"""Tiny unit tests for Website Chat operation/credit FSM (Worker 1 scope)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models.base import Base
from services.web_chat.operation import WebChatOperationRepository, build_turn_payload
from services.web_chat.operation_fsm import (
    OperationFsmError,
    OperationState,
    VerifiedSessionSnapshot,
    assert_transition,
    canonical_payload_hash,
    is_visible_state,
    may_release_credit,
)


def test_canonical_payload_hash_is_stable() -> None:
    payload = build_turn_payload(session_id="sid-1", content="Hello")
    assert canonical_payload_hash(payload) == canonical_payload_hash(dict(payload))


def test_transition_rules_enforced() -> None:
    assert_transition(OperationState.CLAIMED, OperationState.RESERVED)
    with pytest.raises(OperationFsmError):
        assert_transition(OperationState.CLAIMED, OperationState.COMPLETE)


def test_visible_states_never_release() -> None:
    assert is_visible_state(OperationState.DURABLE_VISIBLE)
    assert not may_release_credit(OperationState.DURABLE_VISIBLE)
    assert may_release_credit(OperationState.RESERVED)


def test_operation_claim_conflict_on_payload_mismatch(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    repo = WebChatOperationRepository()
    snapshot = VerifiedSessionSnapshot(
        tenant_id="tenant-a",
        widget_key="wk-a",
        session_id="visitor-1",
        authority_hash="hash",
    )
    with Session() as db:
        first = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=build_turn_payload(session_id="visitor-1", content="Hello"),
            snapshot=snapshot,
            lease_owner="worker-a",
        )
        assert first.status == "created"
        second = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=build_turn_payload(session_id="visitor-1", content="Different"),
            snapshot=snapshot,
            lease_owner="worker-b",
        )
        assert second.status == "conflict"


def test_operation_replay_same_payload(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops2.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    repo = WebChatOperationRepository()
    snapshot = VerifiedSessionSnapshot(
        tenant_id="tenant-a",
        widget_key="wk-a",
        session_id="visitor-1",
        authority_hash="hash",
    )
    payload = build_turn_payload(session_id="visitor-1", content="Hello")
    with Session() as db:
        created = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-a",
        )
        for state in (
            OperationState.RESERVED,
            OperationState.REPLY_READY,
            OperationState.DURABLE_VISIBLE,
            OperationState.CAPTURED,
            OperationState.COMPLETE,
        ):
            repo.transition(
                db,
                tenant_id="tenant-a",
                operation_key="visitor-1:msg-1",
                target=state,
                lease_owner="worker-a",
                lease_generation=1,
                result={"reply_text": "Hi there"},
            )
        replay = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-b",
        )
    assert created.status == "created"
    assert replay.status == "replay"
    assert replay.record is not None
    assert replay.record.canonical_reply() == "Hi there"


def test_operation_in_progress_when_other_worker_holds_reply_ready_lease(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops3.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    repo = WebChatOperationRepository()
    snapshot = VerifiedSessionSnapshot(
        tenant_id="tenant-a",
        widget_key="wk-a",
        session_id="visitor-1",
        authority_hash="hash",
    )
    payload = build_turn_payload(session_id="visitor-1", content="Hello")
    with Session() as db:
        repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-a",
        )
        repo.transition(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            target=OperationState.RESERVED,
            lease_owner="worker-a",
            lease_generation=1,
        )
        repo.transition(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            target=OperationState.REPLY_READY,
            lease_owner="worker-a",
            lease_generation=1,
            result={"reply_text": "Hi there"},
        )
        db.commit()
    with Session() as db:
        blocked = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-b",
        )
    assert blocked.status == "in_progress"


def test_operation_resume_after_expired_reply_ready_lease(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from services.web_chat.operation import _get_row
    from services.web_chat.pg_models import WebChatOperationRow

    engine = create_engine(f"sqlite:///{tmp_path / 'ops4.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    repo = WebChatOperationRepository()
    snapshot = VerifiedSessionSnapshot(
        tenant_id="tenant-a",
        widget_key="wk-a",
        session_id="visitor-1",
        authority_hash="hash",
    )
    payload = build_turn_payload(session_id="visitor-1", content="Hello")
    with Session() as db:
        repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-a",
        )
        repo.transition(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            target=OperationState.REPLY_READY,
            lease_owner="worker-a",
            lease_generation=1,
            result={"reply_text": "Hi there"},
        )
        row = _get_row(db, tenant_id="tenant-a", operation_key="visitor-1:msg-1")
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        db.commit()
    with Session() as db:
        reclaimed = repo.claim(
            db,
            tenant_id="tenant-a",
            operation_key="visitor-1:msg-1",
            payload=payload,
            snapshot=snapshot,
            lease_owner="worker-b",
        )
        row = db.scalars(
            select(WebChatOperationRow).where(WebChatOperationRow.operation_key == "visitor-1:msg-1")
        ).first()
    assert reclaimed.status == "resume"
    assert reclaimed.record is not None
    assert reclaimed.record.lease_owner == "worker-b"
    assert row is not None
    assert row.lease_owner == "worker-b"
