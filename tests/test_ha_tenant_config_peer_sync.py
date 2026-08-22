"""Tests for HA tenant configuration peer sync."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from services.cm.schemas import PublishedPointer
from services.ha_tenant_config_peer_sync import _reconcile_published_cm


def test_reconcile_published_cm_pushes_when_local_is_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    newer = PublishedPointer(
        content_version_id="content_v2",
        index_version_id="index_v2",
        checksums={},
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
        updated_at=datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    older_payload = {
        "content_version_id": "content_v1",
        "index_version_id": "index_v1",
        "checksums": {},
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_version": "1",
        "embedding_dimensions": 1536,
        "updated_at": "2026-08-23T11:00:00+00:00",
    }
    pushed: list[str] = []

    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.read_published_pointer",
        lambda _tenant: newer,
    )
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync._remote_json",
        lambda _path: older_payload,
    )
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync._pointer_digest",
        lambda _tenant: "local",
    )
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.replicate_published_cm_to_peer",
        lambda **kwargs: pushed.append("push"),
    )

    result = _reconcile_published_cm("linas")
    assert result == "cm_published=pushed"
    assert pushed == ["push"]
