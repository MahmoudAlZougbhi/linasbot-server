"""Soak inbound creates skip extra Firestore fence reads. Production still fences."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services.scale.inbound_event_persist import persist_created_inbound


def test_soak_create_skips_shared_fence_reads(monkeypatch: pytest.MonkeyPatch) -> None:

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
        event_id="ibe_soak",
        updated_at=1.0,
        payload={"_linas_soak_simulation": True},
        to_dict=lambda: {"event_id": "ibe_soak", "payload": {"_linas_soak_simulation": True}},
    )
    persist_created_inbound(record, binding_id="b1", enforce_binding_deletion_fence=True)
    assert seen["skip_shared_fence_reads"] is True


def test_production_create_still_reads_shared_fence(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert seen["skip_shared_fence_reads"] is False
