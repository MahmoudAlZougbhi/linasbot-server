"""Embedding provider package."""

from __future__ import annotations

from services.retrieval_v2.providers.fake_embeddings import FakeEmbeddingProvider
from services.retrieval_v2.providers.gemini_embeddings import GeminiEmbeddingProvider

__all__ = ["FakeEmbeddingProvider", "GeminiEmbeddingProvider"]
