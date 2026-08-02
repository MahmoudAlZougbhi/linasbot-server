"""Configurable embedding provider for the CM semantic index (plan D11 / Phase 5).

``CM_EMBEDDING_PROVIDER=hash`` gives a dependency-free, fully deterministic embedder for
tests/dev. The default ``openai`` provider uses the existing OpenAI-compatible client.
Provider/model/version/dimensions are always pinned so index/version manifests can prove
which embedding produced them (plan §13.3 referential integrity / D11).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

HASH_EMBEDDING_DIMENSIONS = 64
OPENAI_EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSIONS_DEFAULT = 1536
EMBEDDING_MANIFEST_VERSION = "1"


def embedding_provider_name() -> str:
    return (os.getenv("CM_EMBEDDING_PROVIDER") or "openai").strip().lower()


@dataclass(frozen=True)
class EmbeddingPinInfo:
    provider: str
    model: str
    version: str
    dimensions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "dimensions": self.dimensions,
        }


def embedding_pin() -> EmbeddingPinInfo:
    """Pin provider/model/version/dimensions for the currently configured provider."""
    provider = embedding_provider_name()
    if provider == "hash":
        return EmbeddingPinInfo(
            provider="hash",
            model="deterministic-hash-v1",
            version=EMBEDDING_MANIFEST_VERSION,
            dimensions=HASH_EMBEDDING_DIMENSIONS,
        )
    model = (
        os.getenv("CM_EMBEDDING_MODEL") or OPENAI_EMBEDDING_MODEL_DEFAULT
    ).strip() or OPENAI_EMBEDDING_MODEL_DEFAULT
    dims_raw = os.getenv("CM_EMBEDDING_DIMENSIONS")
    try:
        dims = int(dims_raw) if dims_raw else OPENAI_EMBEDDING_DIMENSIONS_DEFAULT
    except ValueError:
        dims = OPENAI_EMBEDDING_DIMENSIONS_DEFAULT
    return EmbeddingPinInfo(provider="openai", model=model, version=EMBEDDING_MANIFEST_VERSION, dimensions=dims)


def _hash_embed_one(text: str, dimensions: int = HASH_EMBEDDING_DIMENSIONS) -> list[float]:
    """Deterministic bag-of-tokens hash embedding (no network, no randomness)."""
    normalized = (text or "").strip().lower()
    vector = [0.0] * dimensions
    if not normalized:
        return vector
    tokens = normalized.split() or [normalized]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(dimensions):
            byte = digest[i % len(digest)]
            vector[i] += (byte / 255.0) * 2.0 - 1.0
    norm = sum(v * v for v in vector) ** 0.5
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


async def embed_texts(texts: list[str], *, provider: str | None = None) -> list[list[float]]:
    """Embed a batch of texts using the configured (or explicitly overridden) provider."""
    if not texts:
        return []
    resolved_provider = (provider or embedding_provider_name()).strip().lower()
    if resolved_provider == "hash":
        return [_hash_embed_one(text) for text in texts]
    return await _openai_embed_texts(texts)


async def _openai_embed_texts(texts: list[str]) -> list[list[float]]:
    from services.llm_core_service import client as openai_client

    pin = embedding_pin()
    response = await openai_client.embeddings.create(model=pin.model, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
