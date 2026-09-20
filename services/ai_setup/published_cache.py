"""Process cache for load_published_content (tenant + revision). Invalidate on publish."""

from __future__ import annotations

import threading
from typing import Any

from services.ai_setup.constants import require_tenant_id
from services.ai_setup.schemas import PublishedPointer

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[str, PublishedPointer, dict[str, dict[str, Any]]]] = {}
DISK_LOADS = 0


def invalidate_published_cache(tenant_id: str | None = None) -> None:
    tid = (tenant_id or "").strip()
    with _LOCK:
        if tid:
            _CACHE.pop(tid, None)
        else:
            _CACHE.clear()
    try:
        from services.brain.retrieve.query_embed import invalidate_query_embeds

        invalidate_query_embeds(tid or None)
    except Exception:
        pass
    try:
        from services.brain.compiler.chunk_store import invalidate_chunk_cache

        invalidate_chunk_cache(tid or None)
    except Exception:
        pass


def load_published_content_cached(
    tenant_id: str | None,
) -> tuple[PublishedPointer, dict[str, dict[str, Any]]]:
    """One disk load per tenant+content_version_id; never share across tenants."""
    global DISK_LOADS
    from services.ai_setup.version_store import (
        PublishedVersionError,
        load_published_content_from_disk,
        read_published_pointer,
    )

    tid = require_tenant_id(tenant_id)
    pointer = read_published_pointer(tid)
    if pointer is None:
        raise PublishedVersionError("No published CM version pointer for tenant.")
    version_id = str(pointer.content_version_id or "")
    with _LOCK:
        hit = _CACHE.get(tid)
        if hit is not None and hit[0] == version_id:
            return hit[1], hit[2]
    loaded_pointer, sections = load_published_content_from_disk(tid)
    DISK_LOADS += 1
    with _LOCK:
        _CACHE[tid] = (str(loaded_pointer.content_version_id or ""), loaded_pointer, sections)
    return loaded_pointer, sections
