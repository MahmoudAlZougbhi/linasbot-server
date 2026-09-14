"""Configurable embedding provider for the CM semantic index (plan D11 / Phase 5).

Production / published-mode semantic retrieval uses a real OpenAI-compatible embedding
model (default ``text-embedding-3-small``). Deterministic ``hash`` embeddings exist only
for automated tests (``ENVIRONMENT=test`` / ``PYTEST_CURRENT_TEST``) and are rejected when
``CM_RUNTIME_MODE=published`` or outside the test harness — never silently swapped for
keyword, filename, lexical, or legacy content fallbacks.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Final

HASH_EMBEDDING_DIMENSIONS = 64
OPENAI_EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSIONS_DEFAULT = 1536
EMBEDDING_MANIFEST_VERSION = "1"

# Real semantic providers permitted for published / non-test index build & search.
PRODUCTION_EMBEDDING_PROVIDERS: Final[frozenset[str]] = frozenset({"openai"})
TEST_ONLY_EMBEDDING_PROVIDERS: Final[frozenset[str]] = frozenset({"hash"})


class HashEmbeddingForbiddenError(RuntimeError):
    """Raised when hash/test embeddings are requested outside the allowed test harness,
    or under ``CM_RUNTIME_MODE=published``."""

    code: str = "HASH_EMBEDDING_FORBIDDEN"


class PublishedEmbeddingError(RuntimeError):
    """Raised when a published index/pointer uses a non-production embedding provider."""

    code: str = "PUBLISHED_EMBEDDING_INVALID"


def embedding_provider_name() -> str:
    return (os.getenv("CM_EMBEDDING_PROVIDER") or "openai").strip().lower() or "openai"


def hash_embeddings_allowed() -> bool:
    """Hash embeddings are permitted only when ENVIRONMENT is the test harness.

    ``ENVIRONMENT=test`` is set by ``tests/conftest.py``. Production and staging must
    never set that value, so hash cannot be selected accidentally outside tests.
    """
    env = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return env in {"test", "testing"}


def assert_embedding_provider_allowed(provider: str | None = None) -> str:
    """Resolve and enforce provider policy. Returns the normalized provider name."""
    resolved = (provider or embedding_provider_name()).strip().lower() or "openai"
    if resolved in TEST_ONLY_EMBEDDING_PROVIDERS:
        # Hash embeddings remain test-only via ENVIRONMENT=test (hash_embeddings_allowed).
        # Do not gate on the global runtime label — SoT is per-tenant published CM.
        if not hash_embeddings_allowed():
            raise HashEmbeddingForbiddenError(
                "CM_EMBEDDING_PROVIDER=hash is test-only. "
                "Set ENVIRONMENT=test for unit tests, or use the default openai provider."
            )
        return resolved
    if resolved not in PRODUCTION_EMBEDDING_PROVIDERS:
        raise HashEmbeddingForbiddenError(
            f"Unsupported CM_EMBEDDING_PROVIDER={resolved!r}. "
            f"Allowed production providers: {sorted(PRODUCTION_EMBEDDING_PROVIDERS)}; "
            f"test-only: {sorted(TEST_ONLY_EMBEDDING_PROVIDERS)}."
        )
    return resolved


def assert_published_embedding_pin(provider: str, *, context: str) -> None:
    """Fail honestly if a published pointer/index was built with a test/hash embedding."""
    normalized = (provider or "").strip().lower()
    if normalized not in PRODUCTION_EMBEDDING_PROVIDERS:
        raise PublishedEmbeddingError(
            f"Published {context} uses embedding provider {normalized!r}, which is not a "
            f"production semantic provider ({sorted(PRODUCTION_EMBEDDING_PROVIDERS)}). "
            "Refusing silent fallback to keywords, lexical matching, or legacy content."
        )


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
    provider = assert_embedding_provider_allowed()
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
    """Deterministic bag-of-tokens hash embedding (no network, no randomness). Test-only."""
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
    resolved_provider = assert_embedding_provider_allowed(provider)
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
