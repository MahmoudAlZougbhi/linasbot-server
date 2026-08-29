"""Soak inbound creates use one Firestore create and skip the local ledger flock."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import AlreadyExists

from services.scale.inbound_event_persist import persist_created_inbound


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeRef:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.create_error: Exception | None = None
        self.existing: dict[str, Any] | None = None

    def create(self, document: dict[str, Any]) -> None:
        if self.create_error is not None:
            raise self.create_error
        self.created.append(dict(document))

    def get(self) -> _FakeSnapshot:
        return _FakeSnapshot(self.existing)


def test_soak_create_uses_direct_firestore_create(monkeypatch: pytest.MonkeyPatch) -> None:
    ref = _FakeRef()
    fence_calls: list[object] = []
    cache_calls: list[object] = []
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: object())
    monkeypatch.setattr(
        "services.meta_inbound_deletion_fence._firestore_event_ref",
        lambda *_a, **_k: ref,
    )
    monkeypatch.setattr(
        "services.meta_inbound_deletion_fence.create_firestore_event_unless_fenced",
        lambda **kwargs: fence_calls.append(kwargs) or ({}, True),
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_persist.cache_local_inbound_document",
        lambda **kwargs: cache_calls.append(kwargs) or kwargs["document"],
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_persist.reject_if_locally_fenced",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("soak must skip local fence")),
    )
    record = SimpleNamespace(
        event_id="ibe_soak",
        updated_at=1.0,
        payload={"_linas_soak_simulation": True},
        to_dict=lambda: {"event_id": "ibe_soak", "payload": {"_linas_soak_simulation": True}},
    )
    document, created = persist_created_inbound(
        record, binding_id="b1", enforce_binding_deletion_fence=True
    )
    assert created is True
    assert document["event_id"] == "ibe_soak"
    assert document["revision"] == 1
    assert len(ref.created) == 1
    assert fence_calls == []
    assert cache_calls == []


def test_soak_create_returns_existing_row_on_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    ref = _FakeRef()
    ref.create_error = AlreadyExists("row exists")
    ref.existing = {"event_id": "ibe_soak", "state": "queued"}
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: object())
    monkeypatch.setattr(
        "services.meta_inbound_deletion_fence._firestore_event_ref",
        lambda *_a, **_k: ref,
    )
    record = SimpleNamespace(
        event_id="ibe_soak",
        updated_at=1.0,
        payload={"_linas_soak_simulation": True},
        to_dict=lambda: {"event_id": "ibe_soak"},
    )
    document, created = persist_created_inbound(
        record, binding_id="b1", enforce_binding_deletion_fence=True
    )
    assert created is False
    assert document["state"] == "queued"


def test_production_create_still_uses_fenced_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        "services.scale.inbound_event_persist.reject_if_locally_fenced",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_persist.cache_local_inbound_document",
        lambda **kwargs: kwargs["document"],
    )

    def fake_create(**kwargs: Any) -> tuple[dict[str, Any], bool]:
        seen.update(kwargs)
        return kwargs["document"], True

    monkeypatch.setattr(
        "services.meta_inbound_deletion_fence.create_firestore_event_unless_fenced",
        fake_create,
    )
    record = SimpleNamespace(
        event_id="ibe_live",
        updated_at=1.0,
        payload={"text": "hi"},
        to_dict=lambda: {"event_id": "ibe_live"},
    )
    persist_created_inbound(record, binding_id="b1", enforce_binding_deletion_fence=True)
    assert seen["event_id"] == "ibe_live"
    assert "skip_shared_fence_reads" not in seen
