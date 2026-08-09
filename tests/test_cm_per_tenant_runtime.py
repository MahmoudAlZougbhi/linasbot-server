"""Wave 2: per-tenant published CM SoT + self-service publish defaults."""

from __future__ import annotations

from services.cm.constants import (
    cm_emergency_force_legacy,
    cm_publish_enabled,
    cm_runtime_mode,
    tenant_allows_legacy_bridge,
    tenant_uses_cm_runtime,
)


def test_self_service_publish_default_on(monkeypatch) -> None:
    monkeypatch.delenv("CM_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("CM_EMERGENCY_DISABLE_PUBLISH", raising=False)
    assert cm_publish_enabled() is True


def test_emergency_disable_publish(monkeypatch) -> None:
    monkeypatch.setenv("CM_EMERGENCY_DISABLE_PUBLISH", "true")
    assert cm_publish_enabled() is False


def test_tenant_uses_cm_when_published(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CM_EMERGENCY_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))

    from services.cm.schemas import PublishedPointer
    from services.cm.version_store import write_published_pointer

    write_published_pointer(
        "acme-gym",
        PublishedPointer(
            content_version_id="v1",
            index_version_id=None,
            checksums={},
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            embedding_dimensions=1536,
        ),
    )
    assert tenant_uses_cm_runtime("acme-gym") is True
    assert tenant_allows_legacy_bridge("acme-gym") is False


def test_new_tenant_without_publish_no_legacy_bridge(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CM_EMERGENCY_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    assert tenant_uses_cm_runtime("brand-new") is False
    assert tenant_allows_legacy_bridge("brand-new") is False


def test_linas_without_publish_allows_legacy_bridge(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CM_EMERGENCY_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    assert tenant_uses_cm_runtime("linas") is False
    assert tenant_allows_legacy_bridge("linas") is True


def test_emergency_force_legacy(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CM_EMERGENCY_FORCE_LEGACY", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from services.cm.schemas import PublishedPointer
    from services.cm.version_store import write_published_pointer

    write_published_pointer(
        "acme-gym",
        PublishedPointer(
            content_version_id="v1",
            index_version_id=None,
            checksums={},
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            embedding_dimensions=1536,
        ),
    )
    assert cm_emergency_force_legacy() is True
    assert cm_runtime_mode() == "legacy"
    assert tenant_uses_cm_runtime("acme-gym") is False
    assert tenant_allows_legacy_bridge("linas") is True
