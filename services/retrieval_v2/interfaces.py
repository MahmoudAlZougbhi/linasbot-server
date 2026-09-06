"""Retrieval V2 provider/store contracts (Phase 0)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from services.retrieval_v2.schemas import DenseSearchHit, SearchDocument


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Dense embedding provider. Customer AI must not import Gemini SDK directly."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (asymmetric retrieval formatting when supported)."""

    async def embed_documents(self, texts: list[str], *, titles: list[str] | None = None) -> list[list[float]]:
        """Embed document texts in batches. ``titles`` optional, same length as texts."""

    async def health_check(self) -> dict[str, object]:
        """Return provider readiness without requiring a paid call when possible."""


@runtime_checkable
class SearchStore(Protocol):
    """Vector search store. Every search/mutate requires explicit tenant_id."""

    async def ensure_collection(self, *, dimensions: int) -> None:
        """Create collection if missing; fail if existing dims are incompatible."""

    async def upsert_documents(
        self,
        *,
        tenant_id: str,
        documents: list[SearchDocument],
        vectors: list[list[float]],
    ) -> list[str]:
        """Idempotent upsert. Returns point ids."""

    async def delete_documents(self, *, tenant_id: str, point_ids: list[str]) -> int:
        """Hard delete points scoped to tenant_id."""

    async def deactivate_documents(self, *, tenant_id: str, point_ids: list[str]) -> int:
        """Soft-deactivate (active=false) points scoped to tenant_id."""

    async def search_dense(
        self,
        *,
        tenant_id: str,
        query_vector: list[float],
        limit: int = 10,
        source_types: list[str] | None = None,
        active_only: bool = True,
    ) -> list[DenseSearchHit]:
        """Dense ANN search. tenant_id is mandatory (no global search API)."""

    async def health_check(self) -> dict[str, object]:
        """Connectivity + collection compatibility."""
