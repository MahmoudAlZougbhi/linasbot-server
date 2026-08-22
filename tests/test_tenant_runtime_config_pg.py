"""Tests for Postgres tenant runtime config SoT."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from services.cm.schemas import ActionsSection
from services.tenant_runtime_config_backend import tenant_runtime_config_backend
from services.tenant_runtime_config_pg_store import RevisionConflictError, upsert_draft_row


@pytest.fixture(autouse=True)
def _postgres_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_TENANT_RUNTIME_CONFIG_BACKEND", "postgres")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    from db.models.base import Base
    from db.session import get_engine

    Base.metadata.create_all(get_engine(require=True))


def test_backend_defaults_to_postgres_when_db_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_TENANT_RUNTIME_CONFIG_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    assert tenant_runtime_config_backend() == "postgres"


def test_draft_revision_cas_conflict() -> None:
    from db.session import whatsapp_session

    with whatsapp_session() as session:
        upsert_draft_row(
            session,
            tenant_id="linas",
            section="actions",
            expected_revision=-1,
            revision=1,
            etag='"1-abc"',
            payload={"items": []},
            updated_by="test",
        )
        with pytest.raises(RevisionConflictError):
            upsert_draft_row(
                session,
                tenant_id="linas",
                section="actions",
                expected_revision=0,
                revision=2,
                etag='"2-def"',
                payload={"items": []},
                updated_by="test",
            )


def test_load_actions_section_reads_postgres_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.tenant_runtime_config_service import save_actions_payload

    actions = ActionsSection(items=[{"id": "respond_facebook_dm", "enabled": True}])
    save_actions_payload(
        tenant_id="linas",
        actions_payload=actions.model_dump(),
        expected_published_revision=None,
        published_meta={"content_version_id": "v_test", "index_version_id": "idx_test"},
    )
    from services.cm.actions import load_actions_section

    loaded = load_actions_section("linas")
    assert loaded is not None
    assert loaded.items[0].enabled is True
