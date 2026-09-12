"""Indexing pipeline skeleton: SearchDocument → embed → Qdrant upsert."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.retrieval_index.jobs import IndexJob, IndexOperation
from services.retrieval_v2.errors import RetrievalV2ValidationError, SearchTenantRequiredError
from services.retrieval_v2.interfaces import EmbeddingProvider, SearchStore
from services.retrieval_v2.schemas import SearchDocument, content_sha256
from services.retrieval_v2.trace import RetrievalV2Trace, TraceTimer, new_operation_id


@dataclass(frozen=True)
class IndexPipelineResult:
    status: str
    tenant_id: str
    operation: str
    point_ids: tuple[str, ...]
    content_checksum: str
    duration_ms: float
    embedding_model: str = ""
    embedding_dimensions: int = 0
    error: str = ""


class IndexPipeline:
    """Foundation pipeline. Not subscribed to CM publish events in Phase 1."""

    def __init__(self, *, embeddings: EmbeddingProvider, store: SearchStore) -> None:
        self._embeddings = embeddings
        self._store = store

    async def run_upsert(self, document: SearchDocument) -> IndexPipelineResult:
        timer = TraceTimer()
        tid = (document.tenant_id or "").strip()
        if not tid:
            raise SearchTenantRequiredError("tenant_id is required")
        expected = content_sha256(document.semantic_text)
        if document.content_sha256 and document.content_sha256 != expected:
            raise RetrievalV2ValidationError("content_sha256 does not match semantic_text")
        vectors = await self._embeddings.embed_documents(
            [document.semantic_text],
            titles=[document.title or ""],
        )
        enriched = document.with_embedding_meta(
            model=self._embeddings.model_id,
            dimensions=self._embeddings.dimensions,
        )
        point_ids = await self._store.upsert_documents(
            tenant_id=tid,
            documents=[enriched],
            vectors=vectors,
        )
        return IndexPipelineResult(
            status="ok",
            tenant_id=tid,
            operation=IndexOperation.UPSERT.value,
            point_ids=tuple(point_ids),
            content_checksum=enriched.content_sha256,
            duration_ms=timer.ms(),
            embedding_model=self._embeddings.model_id,
            embedding_dimensions=self._embeddings.dimensions,
        )

    async def run_job(self, job: IndexJob, *, document: SearchDocument | None = None) -> IndexPipelineResult:
        timer = TraceTimer()
        if job.operation == IndexOperation.UPSERT:
            if document is None:
                raise RetrievalV2ValidationError("UPSERT requires a SearchDocument")
            if document.tenant_id != job.tenant_id:
                raise RetrievalV2ValidationError("document tenant_id must match job tenant_id")
            return await self.run_upsert(document)

        point_ids = [job.point_id] if job.point_id else []
        if not point_ids and document is not None:
            point_ids = [document.point_id]

        if job.operation == IndexOperation.DEACTIVATE:
            count = await self._store.deactivate_documents(tenant_id=job.tenant_id, point_ids=point_ids)
            status = "ok" if count else "noop"
        elif job.operation == IndexOperation.DELETE:
            count = await self._store.delete_documents(tenant_id=job.tenant_id, point_ids=point_ids)
            status = "ok" if count else "noop"
        else:
            raise RetrievalV2ValidationError(f"unsupported operation {job.operation}")

        return IndexPipelineResult(
            status=status,
            tenant_id=job.tenant_id,
            operation=job.operation.value,
            point_ids=tuple(point_ids),
            content_checksum=job.content_checksum,
            duration_ms=timer.ms(),
        )

    def trace_dict(self, result: IndexPipelineResult, **extra: Any) -> dict[str, Any]:
        return RetrievalV2Trace(
            operation_id=new_operation_id(),
            tenant_id=result.tenant_id,
            operation=result.operation,
            provider=self._embeddings.provider_name,
            model=result.embedding_model,
            dimensions=result.embedding_dimensions,
            duration_ms=result.duration_ms,
            status=result.status,
            error_code=result.error,
            extra=dict(extra),
        ).to_dict()
