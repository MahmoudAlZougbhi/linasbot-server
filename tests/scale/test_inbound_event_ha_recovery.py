"""HA regressions for shared inbound-event discovery and AI turn claims."""

from __future__ import annotations

import copy
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import services.outbound_turn_idempotency as turn_claims
import services.scale.inbound_event_store as event_store
from services.scale.inbound_event_reconcile import reconcile_stuck_inbound_events
from services.scale.inbound_event_store import (
    InboundEventRecord,
    InboundEventStoreUnavailableError,
    list_active_inbound_events,
)


class AlreadyExists(Exception):
    pass


class _Snapshot:
    def __init__(self, reference: _Document) -> None:
        self.reference = reference
        self.exists = reference.exists

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.reference.data)


class _Query:
    def __init__(self, documents: list[_Document]) -> None:
        self.documents = documents

    def stream(self) -> list[_Snapshot]:
        return [_Snapshot(document) for document in self.documents if document.exists]


class _Collection:
    def __init__(self, path: str) -> None:
        self.path = path
        self.documents: dict[str, _Document] = {}
        self.query_error: Exception | None = None

    def document(self, document_id: str) -> _Document:
        if document_id not in self.documents:
            self.documents[document_id] = _Document(f"{self.path}/{document_id}", exists=False)
        return self.documents[document_id]

    def where(self, *, filter: Any) -> _Query:
        del filter
        if self.query_error is not None:
            raise self.query_error
        active = event_store.ACTIVE_STATES
        return _Query(
            [
                document
                for document in self.documents.values()
                if document.exists and document.data.get("state") in active
            ]
        )


class _Document:
    def __init__(self, path: str, *, exists: bool = True) -> None:
        self.path = path
        self.exists = exists
        self.data: dict[str, Any] = {}
        self._collections: dict[str, _Collection] = {}

    def collection(self, name: str) -> _Collection:
        if name not in self._collections:
            self._collections[name] = _Collection(f"{self.path}/{name}")
        return self._collections[name]

    def create(self, data: dict[str, Any]) -> None:
        if self.exists:
            raise AlreadyExists
        self.data = copy.deepcopy(data)
        self.exists = True

    def set(self, data: dict[str, Any], *, merge: bool = False) -> None:
        if merge:
            self.data.update(copy.deepcopy(data))
        else:
            self.data = copy.deepcopy(data)
        self.exists = True

    def delete(self) -> None:
        self.exists = False

    def get(self) -> _Snapshot:
        return _Snapshot(self)


class _Firestore:
    def __init__(self) -> None:
        self._collections: dict[str, _Collection] = {}

    def collection(self, name: str) -> _Collection:
        if name not in self._collections:
            self._collections[name] = _Collection(name)
        return self._collections[name]


def _inbound_collection(db: _Firestore) -> _Collection:
    return db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events")


def _claim_collection(db: _Firestore, name: str) -> _Collection:
    return db.collection("artifacts").document("linas-ai-bot-backend").collection(name)


def _event(event_id: str, *, state: str = "accepted", attempts: int = 0) -> InboundEventRecord:
    now = time.time()
    return InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id="linas",
        claim_namespace="meta_social_dm_global",
        claim_key=f"linas:instagram:{event_id}",
        state=state,  # type: ignore[arg-type]
        created_at=now - 300,
        updated_at=now - 180,
        payload={"message_id": event_id, "channel": "instagram", "text": "hello"},
        conversation_key=f"linas:instagram:{event_id}",
        attempts=attempts,
    )


@pytest.fixture()
def ha_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _Firestore]:
    import services.durable_event_claim as durable_claims
    import services.job_queue as job_queue_module
    import utils.utils

    root = tmp_path / "inbound_events"
    root.mkdir()
    claims_root = tmp_path / "logs"
    db = _Firestore()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(turn_claims, "get_firestore_db", lambda: db)
    monkeypatch.setattr(durable_claims, "LOGS_DIR", claims_root)
    monkeypatch.setattr(durable_claims, "ensure_dirs", lambda: claims_root.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(
        job_queue_module,
        "job_queue",
        SimpleNamespace(backend="in_process", production_ready=False),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.pending_delivery_for_claim", lambda _basis: None)
    return root, db


@pytest.mark.asyncio
async def test_ai_turn_release_uses_primary_claim_document_and_allows_peer_retry(
    ha_store: tuple[Path, _Firestore],
) -> None:
    _, db = ha_store
    key_basis = turn_claims._claim_key_basis("customer-1", ["mid-ha-1"], [])
    primary_id = turn_claims._ai_turn_claim_document_id(key_basis)
    legacy_id = turn_claims._legacy_ai_turn_claim_document_id(key_basis)
    primary = _claim_collection(db, "ai_turn_claims")
    legacy = _claim_collection(db, "ai_turn_claims_file")

    # A legacy-only fallback claim must still block a new worker during rollout.
    legacy.document(legacy_id).set({"status": "claimed"})
    assert await turn_claims.try_claim_ai_turn("customer-1", ["mid-ha-1"]) is False
    assert primary.document(primary_id).exists is False
    await turn_claims.release_ai_turn_claim(key_basis)
    assert legacy.document(legacy_id).exists is False

    assert await turn_claims.try_claim_ai_turn("customer-1", ["mid-ha-1"]) is True
    assert primary.document(primary_id).exists is True
    assert legacy.document(legacy_id).exists is False

    await turn_claims.release_ai_turn_claim(key_basis)
    assert primary.document(primary_id).exists is False
    assert legacy.document(legacy_id).exists is False

    # A different worker using the shared database can now acquire the exact key.
    assert await turn_claims.try_claim_ai_turn("customer-1", ["mid-ha-1"]) is True
    await turn_claims.complete_ai_turn_claim(key_basis)
    assert primary.document(primary_id).data["status"] == "completed"
    assert await turn_claims.try_claim_ai_turn("customer-1", ["mid-ha-1"]) is False


def test_watchdog_merges_peer_events_dedupes_and_honors_terminal_primary(
    ha_store: tuple[Path, _Firestore],
) -> None:
    root, db = ha_store
    shared = _inbound_collection(db)

    peer_only = _event("ibe_peer_only", attempts=2)
    duplicated_primary = _event("ibe_duplicate", attempts=4)
    completed_primary = _event("ibe_completed", state="completed", attempts=1)
    for record in (peer_only, duplicated_primary, completed_primary):
        shared.document(record.event_id).set(record.to_dict())

    # This node has an older duplicate and a stale active cache for work that a
    # peer already completed in the primary ledger.
    event_store._file_put(_event("ibe_duplicate", attempts=0))
    event_store._file_put(_event("ibe_completed", state="processing", attempts=0))

    active = list_active_inbound_events(older_than_seconds=30.0)
    assert [record.event_id for record in active] == ["ibe_peer_only", "ibe_duplicate"]
    assert next(record for record in active if record.event_id == "ibe_duplicate").attempts == 4
    assert (root / "ibe_peer_only.json").is_file()
    assert event_store._file_get("ibe_completed").state == "completed"  # type: ignore[union-attr]

    result = reconcile_stuck_inbound_events(older_than_seconds=30.0)
    assert result["examined"] == 2
    assert {action["event_id"] for action in result["actions"]} == {"ibe_peer_only", "ibe_duplicate"}
    assert shared.document("ibe_peer_only").data["attempts"] == 3
    assert shared.document("ibe_duplicate").data["attempts"] == 5
    assert shared.document("ibe_completed").data["state"] == "completed"


def test_shared_inbound_query_failure_is_fail_closed(ha_store: tuple[Path, _Firestore]) -> None:
    _, db = ha_store
    _inbound_collection(db).query_error = RuntimeError("firestore unavailable")

    with pytest.raises(InboundEventStoreUnavailableError, match="Unable to query"):
        list_active_inbound_events(older_than_seconds=0.0)


def test_missing_shared_inbound_store_is_fail_closed_in_production(
    ha_store: tuple[Path, _Firestore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import utils.utils

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: None)

    with pytest.raises(InboundEventStoreUnavailableError, match="unavailable in production"):
        list_active_inbound_events(older_than_seconds=0.0)
