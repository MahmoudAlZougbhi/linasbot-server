"""Voyage embed for owner knowledge. Missing key returns no vector."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from services.brain.flags import voyage_api_key
from services.brain.providers.spaces import ENTITY_DOCUMENT, ENTITY_QUERY
from services.brain.providers.voyage_client import VOYAGE_BASE

logger = logging.getLogger(__name__)


def _retry_after(response: object) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    return str(headers.get("Retry-After", "") or "")


def embed_one(text: str, *, query: bool, feature: str = "owner_embed") -> list[float] | None:
    vectors = embed_batch([text], query=query, feature=feature)
    return vectors[0] if vectors else None


def embed_batch(texts: list[str], *, query: bool, feature: str = "owner_embed") -> list[list[float] | None]:
    """One Voyage request for every non-empty text. 429 retries off the event loop."""
    cleaned = [(item or "").strip() for item in texts]
    output: list[list[float] | None] = [None] * len(cleaned)
    key = voyage_api_key()
    if not key:
        return output
    indexes = [index for index, item in enumerate(cleaned) if item]
    if not indexes:
        return output
    from services.platform.feature_flags import flag_enabled

    if flag_enabled("voyage_cache"):
        from services.owner_portal.embed_cache import take_cached

        space_name = "query" if query else "document"
        hit = take_cached(space_name, [cleaned[index] for index in indexes], query=query)
        if hit is not None:
            for index, vector in zip(indexes, hit, strict=True):
                output[index] = vector
            return output
    space = ENTITY_QUERY if query else ENTITY_DOCUMENT
    payload = {
        "model": space.model,
        "input": [cleaned[index][:8000] for index in indexes],
        "input_type": space.input_mode,
        "output_dimension": space.dimensions,
    }
    rows: list[list[float]] | None = None
    for attempt in range(3):
        try:
            response = httpx.post(
                f"{VOYAGE_BASE}/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=12.0,
            )
            retry_after = _retry_after(response)
            if response.status_code == 429 and attempt < 2:
                from services.owner_portal.voyage_metrics import note_voyage

                note_voyage(feature, 429, retry_after=retry_after)
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code >= 500 or response.status_code == 429:
                from services.owner_portal.voyage_metrics import note_voyage

                note_voyage(feature, response.status_code, retry_after=retry_after)
            response.raise_for_status()
            data = response.json().get("data") or []
            rows = [list(item.get("embedding") or []) for item in data]
            break
        except Exception:
            logger.exception("owner embedding failed")
            if flag_enabled("voyage_retry"):
                from services.owner_portal.embed_queue import enqueue_failed

                enqueue_failed(feature, [cleaned[index] for index in indexes])
            return output
    if not rows or len(rows) != len(indexes):
        return output
    for index, vector in zip(indexes, rows, strict=True):
        if vector:
            output[index] = [float(item) for item in vector]
    if flag_enabled("voyage_cache"):
        from services.owner_portal.embed_cache import store_vector

        space_name = "query" if query else "document"
        for index in indexes:
            stored = output[index]
            if stored:
                store_vector(space_name, cleaned[index], stored, query=query)
    if flag_enabled("voyage_retry") and any(output[index] is None for index in indexes):
        from services.owner_portal.embed_queue import enqueue_failed

        enqueue_failed(feature, [cleaned[index] for index in indexes if output[index] is None])
    return output


async def embed_one_async(text: str, *, query: bool, feature: str = "owner_embed") -> list[float] | None:
    """Run the sync client on a worker thread so backoff cannot block the loop."""
    return await asyncio.to_thread(embed_one, text, query=query, feature=feature)
