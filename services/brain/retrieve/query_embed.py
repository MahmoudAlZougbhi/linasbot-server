"""Reuse one query embedding per (tenant, space, query) until CM publish invalidates."""

from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str, str], list[float]] = {}
_MAX = 128
EMBED_CALLS = 0


def invalidate_query_embeds(tenant_id: str | None = None) -> None:
    tid = (tenant_id or "").strip()
    with _LOCK:
        if not tid:
            _CACHE.clear()
            return
        for key in [k for k in _CACHE if k[0] == tid]:
            _CACHE.pop(key, None)


async def embed_query_vector(space: Any, query: str, *, tenant_id: str) -> tuple[list[float], str]:
    """Return (vector, model). Same query string in one turn hits cache."""
    global EMBED_CALLS
    tid = (tenant_id or "").strip() or "_"
    key = (tid, str(getattr(space, "space_id", "") or ""), query)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            return hit, str(getattr(space, "model", "") or "")
    EMBED_CALLS += 1
    if getattr(space, "endpoint", "") == "contextualized":
        from services.brain.providers.voyage_client import embed_contextual_groups

        groups = await embed_contextual_groups(space, [[query]])
        vectors = groups[0].vectors if groups else []
        if not vectors:
            raise RuntimeError("empty_contextual_query")
        vec = list(vectors[0])
    else:
        from services.brain.providers.voyage_client import embed_texts

        qvec = await embed_texts(space, [query])
        vec = list(qvec.vectors[0])
    with _LOCK:
        if len(_CACHE) >= _MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = vec
    return vec, str(getattr(space, "model", "") or "")
