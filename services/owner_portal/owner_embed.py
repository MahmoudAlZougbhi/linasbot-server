"""Sync Voyage embed for owner knowledge. Missing key returns no vector."""

from __future__ import annotations

import httpx

from services.brain.flags import voyage_api_key
from services.brain.providers.spaces import ENTITY_DOCUMENT, ENTITY_QUERY
from services.brain.providers.voyage_client import VOYAGE_BASE


def embed_one(text: str, *, query: bool) -> list[float] | None:
    cleaned = (text or "").strip()
    key = voyage_api_key()
    if not cleaned or not key:
        return None
    space = ENTITY_QUERY if query else ENTITY_DOCUMENT
    try:
        response = httpx.post(
            f"{VOYAGE_BASE}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": space.model,
                "input": [cleaned[:8000]],
                "input_type": space.input_mode,
                "output_dimension": space.dimensions,
            },
            timeout=12.0,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        vector = data[0].get("embedding") if data else None
    except Exception:
        return None
    if not isinstance(vector, list) or not vector:
        return None
    return [float(item) for item in vector]
