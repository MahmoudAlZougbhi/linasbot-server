"""Shared helpers for CM published-mode tests.

Uses a mocked OpenAI embedding transport with deterministic vectors so tests never
call the network, while still exercising the production ``openai`` provider path
(hash embeddings remain forbidden under ``CM_RUNTIME_MODE=published``).
"""

from __future__ import annotations

from typing import Any

import pytest

from services.cm.embeddings import HASH_EMBEDDING_DIMENSIONS, _hash_embed_one, embedding_pin
from services.cm.schemas import PublishedPointer, default_section_payload
from services.cm.semantic_index import build_index
from services.cm.version_store import write_published_pointer, write_version_content


def install_mocked_openai_embeddings(monkeypatch: pytest.MonkeyPatch, *, published_mode: bool = True) -> None:
    """Force the openai provider with a local deterministic embedder (no network)."""
    monkeypatch.setenv("CM_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("CM_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("CM_EMBEDDING_DIMENSIONS", str(HASH_EMBEDDING_DIMENSIONS))
    if published_mode:
        monkeypatch.setenv("CM_RUNTIME_MODE", "published")
    else:
        monkeypatch.setenv("CM_RUNTIME_MODE", "legacy")

    async def _fake_openai_embed_texts(texts: list[str]) -> list[list[float]]:
        return [_hash_embed_one(text, dimensions=HASH_EMBEDDING_DIMENSIONS) for text in texts]

    monkeypatch.setattr("services.cm.embeddings._openai_embed_texts", _fake_openai_embed_texts)


def base_sections() -> dict[str, dict[str, Any]]:
    from services.cm.constants import CM_SECTIONS

    return {section: default_section_payload(section) for section in CM_SECTIONS}


async def publish_test_content(
    tenant_id: str,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Write version content + openai-labeled semantic index + published pointer."""
    sections = base_sections()
    if overrides:
        sections.update(overrides)

    version_id = f"v_{tenant_id}"
    checksums = write_version_content(tenant_id, version_id, sections)
    index_manifest = await build_index(
        tenant_id=tenant_id,
        content_version_id=version_id,
        sections=sections,
        index_id=f"idx_{tenant_id}",
    )
    index_id = str(index_manifest["index_id"])
    pin = embedding_pin()
    assert pin.provider == "openai"
    pointer = PublishedPointer(
        content_version_id=version_id,
        index_version_id=index_id,
        checksums=checksums,
        embedding_provider=pin.provider,
        embedding_model=pin.model,
        embedding_version=pin.version,
        embedding_dimensions=pin.dimensions,
    )
    write_published_pointer(tenant_id, pointer)
    return version_id, index_id
