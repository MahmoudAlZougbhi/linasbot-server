"""Publish machinery: draft → immutable version → semantic index → pointer flip (plan §13.3).

Guarded by :func:`services.cm.publish_gate.ensure_publish_enabled` (hard-403 upstream in
``cm_api`` when ``CM_PUBLISH_ENABLED`` is not true). Runs under :func:`tenant_server_lock` so a
publish/rollback is atomic with respect to other publish/rollback calls for the same tenant.

Rollback restores BOTH pointer fields (content + index version ids) together — plan §12 step 2
requires there to be exactly one published version at any moment, so a partial pointer (content
from one version, index from another) must never be observable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.embeddings import embedding_pin
from services.cm.schemas import EmbeddingPin, PublishedPointer, PublishManifest, utc_now
from services.cm.semantic_index import build_index
from services.cm.storage import get_draft, tenant_server_lock
from services.cm.validation import validate_cm
from services.cm.version_store import (
    read_published_pointer,
    read_version_content,
    read_version_manifest,
    write_published_pointer,
    write_version_content,
    write_version_manifest,
)


class PublishBlockedError(RuntimeError):
    """Raised when draft validation has hard errors that must block publish."""

    def __init__(self, message: str, *, errors: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.message = message
        self.errors = errors


class RollbackTargetError(RuntimeError):
    """Raised when a rollback target version_id has no manifest/content."""


@dataclass
class PublishResult:
    tenant_id: str
    content_version_id: str
    index_version_id: str
    manifest: dict[str, Any]
    pointer: dict[str, Any]
    previous_pointer: dict[str, Any] | None


def _normalize_tenant(tenant_id: str | None) -> str:
    return (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID


def _collect_draft_sections(tenant_id: str) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for name in CM_SECTIONS:
        envelope = get_draft(name, tenant_id=tenant_id, create_default=True)
        sections[name] = dict(envelope.payload)
    return sections


async def publish_draft(
    *,
    tenant_id: str | None = None,
    published_by: str = "unknown",
    notes: str | None = None,
) -> PublishResult:
    """Atomically publish the current draft as the tenant's new (and only) published version.

    Caller MUST have already checked :func:`services.cm.publish_gate.ensure_publish_enabled`.
    Hard validation errors (restricted conflicts, notes overriding structured facts) block
    publish — there is no way to publish an internally-inconsistent version.

    Validation / content-write / index-build (which may ``await`` a real embedding provider)
    intentionally run OUTSIDE ``tenant_server_lock``: each writes to a brand-new, unique
    ``content_version_id``/``index_id`` path, so there is no cross-request contention, and an
    ``await`` is never held while blocking the OS-level tenant lock (asyncio-safe). Only the
    final pointer flip — a tiny, synchronous read-then-write — is done under the lock, so two
    concurrent publishes for the same tenant can never interleave a partial pointer.
    """
    return await publish_draft_sections(
        tenant_id=tenant_id,
        published_by=published_by,
        notes=notes,
        section_names=None,
    )


async def publish_draft_sections(
    *,
    tenant_id: str | None = None,
    published_by: str = "unknown",
    notes: str | None = None,
    section_names: list[str] | tuple[str, ...] | None = None,
) -> PublishResult:
    """Publish draft sections; when ``section_names`` is set, overlay only those onto the
    currently published content (FAQ-only / pricing-only publishes without dirty other drafts).
    """
    tid = _normalize_tenant(tenant_id)

    validation = validate_cm(tenant_id=tid)
    if not validation["ok"]:
        raise PublishBlockedError(
            f"Publish blocked: {validation['error_count']} validation error(s).",
            errors=validation["errors"],
        )

    allowed = {str(s).strip() for s in (section_names or []) if str(s).strip()}
    if allowed:
        unknown = sorted(allowed - set(CM_SECTIONS))
        if unknown:
            raise PublishBlockedError(
                f"Publish blocked: unknown section(s) {unknown}.",
                errors=[{"code": "UNKNOWN_SECTION", "sections": unknown}],
            )
        pointer = read_published_pointer(tid)
        if pointer is None:
            raise PublishBlockedError(
                "Publish blocked: section-scoped publish requires an existing published version.",
                errors=[{"code": "NO_PUBLISHED_BASE"}],
            )
        base = read_version_content(tid, pointer.content_version_id)
        if not base:
            raise PublishBlockedError(
                "Publish blocked: published content unavailable for section overlay.",
                errors=[{"code": "PUBLISHED_CONTENT_MISSING"}],
            )
        sections = {name: dict(base.get(name) or {}) for name in CM_SECTIONS}
        draft_sections = _collect_draft_sections(tid)
        for name in allowed:
            sections[name] = dict(draft_sections[name])
        if notes is None:
            notes = f"section_scoped_publish:{','.join(sorted(allowed))}"
    else:
        sections = _collect_draft_sections(tid)

    content_version_id = f"v_{uuid.uuid4().hex[:12]}"
    checksums = write_version_content(tid, content_version_id, sections)

    index_manifest = await build_index(tenant_id=tid, content_version_id=content_version_id, sections=sections)
    index_version_id = str(index_manifest["index_id"])

    pin = embedding_pin()
    embedding = EmbeddingPin(
        provider=pin.provider,
        model=pin.model,
        version=pin.version,
        dimensions=pin.dimensions,
    )
    manifest = PublishManifest(
        tenant_id=tid,
        content_version_id=content_version_id,
        index_version_id=index_version_id,
        created_at=utc_now(),
        created_by=published_by,
        checksums=checksums,
        embedding=embedding,
        notes=notes,
    )
    write_version_manifest(tid, content_version_id, manifest.model_dump(mode="json"))

    pointer_out = PublishedPointer(
        content_version_id=content_version_id,
        index_version_id=index_version_id,
        checksums=checksums,
        embedding_provider=pin.provider,
        embedding_model=pin.model,
        embedding_version=pin.version,
        embedding_dimensions=pin.dimensions,
        updated_at=utc_now(),
    )
    with tenant_server_lock(tid):
        previous_pointer = read_published_pointer(tid)
        write_published_pointer(tid, pointer_out)

    from services.ai_limits_source import sync_enforcement_from_payload

    sync_enforcement_from_payload(tid, sections.get("ai_limits") or {})

    return PublishResult(
        tenant_id=tid,
        content_version_id=content_version_id,
        index_version_id=index_version_id,
        manifest=manifest.model_dump(mode="json"),
        pointer=pointer_out.model_dump(mode="json"),
        previous_pointer=previous_pointer.model_dump(mode="json") if previous_pointer else None,
    )


async def publish_faq_only(
    *,
    tenant_id: str | None = None,
    published_by: str = "unknown",
    notes: str | None = None,
) -> PublishResult:
    """Atomic FAQ-only publish: draft FAQ over published base + semantic index rebuild."""
    return await publish_draft_sections(
        tenant_id=tenant_id,
        published_by=published_by,
        notes=notes or "faq_only_publish",
        section_names=("faq",),
    )


def rollback_to_version(
    *,
    tenant_id: str | None = None,
    content_version_id: str,
) -> PublishResult:
    """Flip the published pointer back to a prior, already-built version (content + index).

    The target version must already have a manifest (i.e. it was produced by a prior
    :func:`publish_draft` call) — rollback never rebuilds content/index, it only restores an
    existing, checksummed pointer. Both pointer fields move together; never partially.
    """
    tid = _normalize_tenant(tenant_id)

    with tenant_server_lock(tid):
        manifest_dict = read_version_manifest(tid, content_version_id)
        if manifest_dict is None:
            raise RollbackTargetError(f"No manifest found for content_version_id={content_version_id!r}.")
        manifest = PublishManifest.model_validate(manifest_dict)

        previous_pointer = read_published_pointer(tid)
        pointer = PublishedPointer(
            content_version_id=manifest.content_version_id,
            index_version_id=manifest.index_version_id,
            checksums=dict(manifest.checksums),
            embedding_provider=str(manifest.embedding.provider),
            embedding_model=str(manifest.embedding.model),
            embedding_version=str(manifest.embedding.version),
            embedding_dimensions=int(manifest.embedding.dimensions),
            updated_at=utc_now(),
        )
        write_published_pointer(tid, pointer)

        return PublishResult(
            tenant_id=tid,
            content_version_id=pointer.content_version_id,
            index_version_id=pointer.index_version_id or "",
            manifest=manifest_dict,
            pointer=pointer.model_dump(mode="json"),
            previous_pointer=previous_pointer.model_dump(mode="json") if previous_pointer else None,
        )
