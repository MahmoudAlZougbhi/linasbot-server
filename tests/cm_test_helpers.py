"""Shared helpers for CM published-mode tests.

Publish pins Voyage (Brain). Hash embeddings remain test-only for leftover
file-index unit tests. Live publish does not build an OpenAI semantic_index.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.ai_setup.schemas import PublishedPointer, default_section_payload
from services.ai_setup.version_store import write_published_pointer, write_version_content
from services.brain.budgets import DEFAULT_BUDGETS
from services.brain.providers.spaces import ENTITY_MODEL
from services.brain.providers.spaces import PROVIDER as VOYAGE_PROVIDER


def install_mocked_openai_embeddings(monkeypatch: pytest.MonkeyPatch, *, published_mode: bool = True) -> None:
    """Pin published CM mode. Name kept for existing tests; embeddings are Voyage."""
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("CM_EMBEDDING_MODEL", ENTITY_MODEL)
    monkeypatch.setenv("CM_EMBEDDING_DIMENSIONS", str(DEFAULT_BUDGETS.embedding_dimensions))
    if published_mode:
        monkeypatch.setenv("CM_RUNTIME_MODE", "published")
    else:
        monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")


def base_sections() -> dict[str, dict[str, Any]]:
    from services.ai_setup.constants import CM_SECTIONS

    return {section: default_section_payload(section) for section in CM_SECTIONS}


async def publish_test_content(
    tenant_id: str,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Write version content + Voyage-labeled published pointer (no OpenAI file index)."""
    sections = base_sections()
    if overrides:
        sections.update(overrides)

    version_id = f"v_{tenant_id}"
    checksums = write_version_content(tenant_id, version_id, sections)
    index_id = version_id
    pointer = PublishedPointer(
        content_version_id=version_id,
        index_version_id=index_id,
        checksums=checksums,
        embedding_provider=VOYAGE_PROVIDER,
        embedding_model=ENTITY_MODEL,
        embedding_version="1",
        embedding_dimensions=DEFAULT_BUDGETS.embedding_dimensions,
    )
    write_published_pointer(tenant_id, pointer)
    return version_id, index_id


def publish_pointer_content(
    tenant_id: str,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Write published CM content without building a file semantic index."""
    sections = base_sections()
    if overrides:
        sections.update(overrides)
    version_id = f"v_{tenant_id}"
    checksums = write_version_content(tenant_id, version_id, sections)
    write_published_pointer(
        tenant_id,
        PublishedPointer(
            content_version_id=version_id,
            index_version_id=version_id,
            checksums=checksums,
            embedding_provider=VOYAGE_PROVIDER,
            embedding_model=ENTITY_MODEL,
            embedding_version="1",
            embedding_dimensions=DEFAULT_BUDGETS.embedding_dimensions,
        ),
    )
    from services.brain.reply.manifest import clear_manifest_cache

    clear_manifest_cache()
    return version_id
