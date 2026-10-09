"""Cache Voyage vectors by model and normalized text. Off unless the flag is on."""

from __future__ import annotations

import hashlib

_CACHE: dict[tuple[str, str, bool], list[float]] = {}


def reset_embed_cache_for_tests() -> None:
    _CACHE.clear()


def cache_key(model: str, text: str, *, query: bool) -> tuple[str, str, bool]:
    normalized = " ".join((text or "").split())
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return (model, digest, query)


def cached_vector(model: str, text: str, *, query: bool) -> list[float] | None:
    return _CACHE.get(cache_key(model, text, query=query))


def store_vector(model: str, text: str, vector: list[float], *, query: bool) -> None:
    _CACHE[cache_key(model, text, query=query)] = list(vector)


def take_cached(model: str, texts: list[str], *, query: bool) -> list[list[float]] | None:
    found: list[list[float]] = []
    for text in texts:
        if not (text or "").strip():
            found.append([])
            continue
        hit = cached_vector(model, text, query=query)
        if hit is None:
            return None
        found.append(hit)
    return found
