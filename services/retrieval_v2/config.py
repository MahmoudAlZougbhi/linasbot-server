"""Retrieval V2 configuration. All feature flags default OFF. No secrets hardcoded."""

from __future__ import annotations

import os

# Bump when SearchDocument / payload / ID scheme changes incompatibly.
INDEX_SCHEMA_VERSION = "v2.0.0"

DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_GEMINI_EMBEDDING_DIMENSIONS = 3072
DEFAULT_QDRANT_COLLECTION = "tenant_business_v2"


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 1_000_000) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(maximum, int(raw)))
    except ValueError:
        return default


def _float_env(name: str, default: float, *, minimum: float = 0.1, maximum: float = 600.0) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(maximum, float(raw)))
    except ValueError:
        return default


def retrieval_v2_enabled() -> bool:
    """Master live flag. Default OFF — must stay off in Phase 0/1."""
    return _truthy("RETRIEVAL_V2_ENABLED", "false")


def retrieval_v2_shadow_enabled() -> bool:
    """Shadow compare flag. Default OFF."""
    return _truthy("RETRIEVAL_V2_SHADOW", "false")


def gemini_api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def gemini_embedding_model() -> str:
    return (
        os.getenv("GEMINI_EMBEDDING_MODEL") or DEFAULT_GEMINI_EMBEDDING_MODEL
    ).strip() or DEFAULT_GEMINI_EMBEDDING_MODEL


def gemini_embedding_dimensions() -> int:
    return _int_env(
        "GEMINI_EMBEDDING_DIMENSIONS",
        DEFAULT_GEMINI_EMBEDDING_DIMENSIONS,
        minimum=128,
        maximum=3072,
    )


def gemini_embedding_timeout_seconds() -> float:
    return _float_env("GEMINI_EMBEDDING_TIMEOUT_SECONDS", 30.0, minimum=1.0, maximum=180.0)


def gemini_embedding_max_batch() -> int:
    return _int_env("GEMINI_EMBEDDING_MAX_BATCH", 32, minimum=1, maximum=128)


def gemini_embedding_max_attempts() -> int:
    return _int_env("GEMINI_EMBEDDING_MAX_ATTEMPTS", 3, minimum=1, maximum=8)


def qdrant_url() -> str:
    return (os.getenv("QDRANT_URL") or "").strip()


def qdrant_api_key() -> str:
    return (os.getenv("QDRANT_API_KEY") or "").strip()


def qdrant_collection() -> str:
    return (os.getenv("QDRANT_COLLECTION") or DEFAULT_QDRANT_COLLECTION).strip() or DEFAULT_QDRANT_COLLECTION


def qdrant_timeout_seconds() -> float:
    return _float_env("QDRANT_TIMEOUT_SECONDS", 10.0, minimum=1.0, maximum=120.0)


def qdrant_prefer_grpc() -> bool:
    return _truthy("QDRANT_PREFER_GRPC", "false")
