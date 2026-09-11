"""Publish lab CM via the real pointer/version store (non-production tenant)."""

from __future__ import annotations

from typing import Any

from services.cm.atomic_io import compute_checksum
from services.cm.paths import ensure_cm_dirs
from services.cm.schemas import PublishedPointer, utc_now
from services.cm.version_store import write_published_pointer, write_version_content
from services.customer_ai.evals.live_lab_corpus import lab_published_sections
from services.customer_ai.providers.spaces import KNOWLEDGE_MODEL


def publish_lab_tenant(tenant_id: str, *, revision: str = "lab_v1") -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    ensure_cm_dirs(tid)
    sections = lab_published_sections()
    checksums = write_version_content(tid, revision, sections)
    # Ensure checksum map covers written sections only.
    checksums = {k: compute_checksum(sections[k]) for k in sections}
    write_version_content(tid, revision, sections)
    pointer = PublishedPointer(
        content_version_id=revision,
        index_version_id=f"idx_{revision}",
        checksums=checksums,
        embedding_provider="voyage",
        embedding_model=KNOWLEDGE_MODEL,
        embedding_version="lab",
        embedding_dimensions=1024,
        updated_at=utc_now(),
    )
    write_published_pointer(tid, pointer)
    return {
        "tenant_id": tid,
        "revision": revision,
        "sections": sorted(sections.keys()),
        "checksums": checksums,
    }
