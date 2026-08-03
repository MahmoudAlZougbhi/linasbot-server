"""Published CM version content storage (plan §13.1 / §13.3).

Layout: ``{DATA_ROOT}/tenants/{tenant_id}/cm/versions/{version_id}/{manifest.json, content/*.json}``.
Loading verifies per-section checksums recorded on the published pointer (referential
integrity) and raises rather than silently falling back when anything is missing/corrupt —
there is exactly ONE published version per tenant, ever (plan §12 step 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.cm.atomic_io import atomic_write_json, compute_checksum, read_json_object
from services.cm.constants import CM_SECTIONS
from services.cm.paths import published_pointer_path, versions_dir
from services.cm.schemas import PublishedPointer

CONTENT_DIRNAME = "content"
MANIFEST_FILENAME = "manifest.json"


class PublishedVersionError(RuntimeError):
    """Raised when the published pointer or its version content is missing/corrupt.

    Callers MUST surface an honest failure/clarification path — never a silent legacy fallback.
    """

    code: str = "PUBLISHED_VERSION_UNAVAILABLE"


def version_dir(tenant_id: str | None, version_id: str) -> Path:
    return versions_dir(tenant_id) / version_id


def version_content_dir(tenant_id: str | None, version_id: str) -> Path:
    return version_dir(tenant_id, version_id) / CONTENT_DIRNAME


def write_version_content(
    tenant_id: str | None,
    version_id: str,
    sections: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Write each section payload under the version's content dir. Returns per-section checksums."""
    content_dir = version_content_dir(tenant_id, version_id)
    checksums: dict[str, str] = {}
    for section, payload in sections.items():
        checksums[section] = atomic_write_json(content_dir / f"{section}.json", payload)
    return checksums


def read_version_content(tenant_id: str | None, version_id: str) -> dict[str, dict[str, Any]] | None:
    content_dir = version_content_dir(tenant_id, version_id)
    if not content_dir.exists():
        return None
    sections: dict[str, dict[str, Any]] = {}
    for section in CM_SECTIONS:
        path = content_dir / f"{section}.json"
        if path.exists():
            sections[section] = read_json_object(path)
    return sections


def write_version_manifest(tenant_id: str | None, version_id: str, manifest: dict[str, Any]) -> None:
    atomic_write_json(version_dir(tenant_id, version_id) / MANIFEST_FILENAME, manifest)


def read_version_manifest(tenant_id: str | None, version_id: str) -> dict[str, Any] | None:
    path = version_dir(tenant_id, version_id) / MANIFEST_FILENAME
    if not path.exists():
        return None
    return read_json_object(path)


def read_published_pointer(tenant_id: str | None = None) -> PublishedPointer | None:
    path = published_pointer_path(tenant_id)
    if not path.exists():
        return None
    try:
        data = read_json_object(path)
        return PublishedPointer.model_validate(data)
    except Exception:
        return None


def write_published_pointer(tenant_id: str | None, pointer: PublishedPointer) -> None:
    atomic_write_json(published_pointer_path(tenant_id), pointer.model_dump(mode="json"))


def load_published_content(tenant_id: str | None = None) -> tuple[PublishedPointer, dict[str, dict[str, Any]]]:
    """Load the tenant's ONE published version content, with checksum verification.

    Raises :class:`PublishedVersionError` on any missing/corrupt state (no legacy fallback).
    """
    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        raise PublishedVersionError("No published CM version pointer for tenant.")

    sections = read_version_content(tenant_id, pointer.content_version_id)
    if sections is None:
        raise PublishedVersionError(f"Published content_version_id={pointer.content_version_id!r} content is missing.")

    for section, checksum in pointer.checksums.items():
        payload = sections.get(section)
        if payload is None:
            continue
        if compute_checksum(payload) != checksum:
            raise PublishedVersionError(
                f"Checksum mismatch for section {section!r} in version {pointer.content_version_id!r}."
            )

    return pointer, sections
