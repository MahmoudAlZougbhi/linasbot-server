"""Published-CM cache hook used by publish/unpublish. Retrieval index is gone."""

from __future__ import annotations

_CACHE: dict[str, object] = {}


def clear_manifest_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _CACHE.clear()
        return
    _CACHE.pop(tenant_id, None)
