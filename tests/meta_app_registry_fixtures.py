"""Pytest fixtures for two-app Meta registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meta_app_registry import MetaAppRegistry


@pytest.fixture
def meta_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-for-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-for-tests")
    monkeypatch.setenv("META_APP_B_ID", "998877665544")
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-for-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-for-tests")
    monkeypatch.setenv("META_APP_B_LOGIN_CONFIG_ID", "config-for-tests")
    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "registry-master-secret-used-only-in-tests-123456789")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.delenv("META_APP_B_LINAS_CUTOVER_APPROVED", raising=False)


@pytest.fixture
def registry(tmp_path: Path, meta_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="registry-master-secret-used-only-in-tests-123456789",
    )
