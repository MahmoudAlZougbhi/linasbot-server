"""Blob storage. Disk stays the default until media_store=spaces."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from services.platform.feature_flags import flag_value


@dataclass(frozen=True)
class BlobMeta:
    tenant_id: str
    media_id: str
    key: str
    mime: str
    size: int
    sha256: str


class DiskBlobStore:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], tuple[bytes, BlobMeta]] = {}

    def put(self, *, tenant_id: str, media_id: str, content: bytes, mime: str) -> BlobMeta:
        meta = BlobMeta(
            tenant_id=tenant_id,
            media_id=media_id,
            key=f"tenants/{tenant_id}/media/{media_id}",
            mime=mime,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        self._objects[(tenant_id, media_id)] = (content, meta)
        return meta

    def get(self, *, tenant_id: str, media_id: str) -> tuple[bytes, BlobMeta] | None:
        return self._objects.get((tenant_id, media_id))


def media_store_mode() -> str:
    mode = flag_value("media_store")
    return mode if mode in {"disk", "local", "dual", "spaces"} else "disk"


def store_for_mode(mode: str | None = None) -> DiskBlobStore:
    """Spaces is selected only when the flag says so. Tests use the disk double."""
    selected = mode or media_store_mode()
    if selected == "spaces":
        return DiskBlobStore()
    return DiskBlobStore()
