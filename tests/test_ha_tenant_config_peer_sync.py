"""Tests for HA tenant configuration cache rebuild."""

from __future__ import annotations

import pytest

from services.ha_tenant_config_peer_sync import run_tenant_config_cache_rebuild


def test_cache_rebuild_skips_file_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.tenant_runtime_config_postgres_required",
        lambda: False,
    )
    result = run_tenant_config_cache_rebuild(tenant_id="linas")
    assert result["skipped"] is True


def test_cache_rebuild_calls_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.tenant_runtime_config_postgres_required",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.rebuild_tenant_cache",
        lambda tenant_id: {"drafts": 2, "tenant": tenant_id},
    )
    monkeypatch.setattr(
        "services.ha_tenant_config_peer_sync.read_published_pointer",
        lambda _tenant: None,
    )
    result = run_tenant_config_cache_rebuild(tenant_id="linas")
    assert result["drafts"] == 2
