"""Tenant-scoped CM filesystem layout (CM subsystem only)."""

from __future__ import annotations

from pathlib import Path

from services.cm.constants import DEFAULT_TENANT_ID
from storage.persistent_storage import get_data_root


def tenant_cm_root(tenant_id: str | None = None) -> Path:
    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    root = Path(get_data_root()) / "tenants" / tid / "cm"
    return root


def draft_dir(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "draft"


def published_pointer_path(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "published" / "pointer.json"


def versions_dir(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "versions"


def indexes_dir(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "indexes"


def snapshots_dir(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "snapshots"


def archive_dir(tenant_id: str | None = None) -> Path:
    return tenant_cm_root(tenant_id) / "archive"


def media_dir(tenant_id: str | None = None) -> Path:
    """Tenant-local binary store for knowledge/care article attachments."""
    return tenant_cm_root(tenant_id) / "media"


def ensure_cm_dirs(tenant_id: str | None = None) -> None:
    for p in (
        draft_dir(tenant_id),
        published_pointer_path(tenant_id).parent,
        versions_dir(tenant_id),
        indexes_dir(tenant_id),
        snapshots_dir(tenant_id),
        archive_dir(tenant_id),
        media_dir(tenant_id),
    ):
        p.mkdir(parents=True, exist_ok=True)
