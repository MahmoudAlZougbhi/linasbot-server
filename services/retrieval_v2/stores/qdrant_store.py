"""Qdrant dense search store for Retrieval V2."""

from __future__ import annotations

import logging
from typing import Any, Callable

from services.retrieval_v2.config import (
    qdrant_api_key,
    qdrant_collection,
    qdrant_prefer_grpc,
    qdrant_timeout_seconds,
    qdrant_url,
)
from services.retrieval_v2.errors import (
    RetrievalV2ValidationError,
    SearchStoreConfigError,
    SearchStoreUnavailableError,
    SearchTenantRequiredError,
)
from services.retrieval_v2.schemas import DenseSearchHit, SearchDocument, SourceType
from services.retrieval_v2.trace import RetrievalV2Trace, TraceTimer, new_operation_id

logger = logging.getLogger(__name__)

# Gemini Embedding 2 vectors are L2-normalized for truncated dims; Cosine matches
# normalized retrieval embeddings in Qdrant.
DENSE_DISTANCE = "Cosine"


def _require_tenant(tenant_id: str) -> str:
    tid = (tenant_id or "").strip()
    if not tid:
        raise SearchTenantRequiredError("tenant_id is required")
    return tid


class QdrantSearchStore:
    """Tenant-scoped dense vector store backed by Qdrant."""

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        timeout_seconds: float | None = None,
        prefer_grpc: bool | None = None,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._url = (url if url is not None else qdrant_url()).strip()
        self._api_key = (api_key if api_key is not None else qdrant_api_key()).strip()
        self._collection = (collection if collection is not None else qdrant_collection()).strip()
        self._timeout = float(timeout_seconds if timeout_seconds is not None else qdrant_timeout_seconds())
        self._prefer_grpc = bool(prefer_grpc if prefer_grpc is not None else qdrant_prefer_grpc())
        self._client = client
        self._client_factory = client_factory
        self._ensured_dims: int | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise SearchStoreConfigError("qdrant-client package is required for QdrantSearchStore") from exc
        if self._url in {":memory:", "memory"}:
            self._client = QdrantClient(location=":memory:")
            return self._client
        if not self._url:
            raise SearchStoreConfigError("QDRANT_URL is required (or pass an in-memory client for tests)")
        kwargs: dict[str, Any] = {
            "url": self._url,
            "timeout": self._timeout,
            "prefer_grpc": self._prefer_grpc,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        self._client = QdrantClient(**kwargs)
        return self._client

    async def ensure_collection(self, *, dimensions: int) -> None:
        if dimensions < 8:
            raise SearchStoreConfigError("dimensions too small")
        client = self._get_client()
        from qdrant_client.http import models as qm

        exists = self._collection_exists(client)
        if exists:
            info = client.get_collection(self._collection)
            existing_size = self._read_vector_size(info)
            if existing_size is not None and int(existing_size) != int(dimensions):
                raise SearchStoreConfigError(
                    f"collection {self._collection!r} has dim={existing_size}, expected {dimensions}"
                )
            self._ensure_payload_indexes(client)
            self._ensured_dims = int(dimensions)
            return

        client.create_collection(
            collection_name=self._collection,
            vectors_config=qm.VectorParams(size=int(dimensions), distance=qm.Distance.COSINE),
        )
        self._ensure_payload_indexes(client)
        self._ensured_dims = int(dimensions)

    def _collection_exists(self, client: Any) -> bool:
        try:
            return bool(client.collection_exists(self._collection))
        except Exception:
            try:
                names = {c.name for c in client.get_collections().collections}
                return self._collection in names
            except Exception as exc:  # noqa: BLE001
                raise SearchStoreUnavailableError(str(exc)) from exc

    def _read_vector_size(self, info: Any) -> int | None:
        vectors = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(vectors, "vectors", None)
        if vectors is None:
            return None
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, dict):
            first = next(iter(vectors.values()), None)
            if first is not None and hasattr(first, "size"):
                return int(first.size)
        return None

    def _ensure_payload_indexes(self, client: Any) -> None:
        from qdrant_client.http import models as qm

        for field_name, schema in (
            ("tenant_id", qm.PayloadSchemaType.KEYWORD),
            ("source_type", qm.PayloadSchemaType.KEYWORD),
            ("active", qm.PayloadSchemaType.BOOL),
            ("published_revision", qm.PayloadSchemaType.KEYWORD),
        ):
            try:
                client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception:
                continue

    async def upsert_documents(
        self,
        *,
        tenant_id: str,
        documents: list[SearchDocument],
        vectors: list[list[float]],
    ) -> list[str]:
        tid = _require_tenant(tenant_id)
        if len(documents) != len(vectors):
            raise RetrievalV2ValidationError("documents/vectors length mismatch")
        if not documents:
            return []
        for doc in documents:
            if doc.tenant_id != tid:
                raise RetrievalV2ValidationError("document tenant_id must match upsert tenant_id")
        dims = len(vectors[0])
        await self.ensure_collection(dimensions=dims)
        client = self._get_client()
        from qdrant_client.http import models as qm

        timer = TraceTimer()
        points = []
        point_ids: list[str] = []
        for doc, vec in zip(documents, vectors):
            if len(vec) != dims:
                raise RetrievalV2ValidationError("inconsistent vector dimensions in batch")
            pid = doc.point_id
            point_ids.append(pid)
            points.append(qm.PointStruct(id=pid, vector=list(vec), payload=doc.to_payload()))
        try:
            client.upsert(collection_name=self._collection, points=points, wait=True)
        except Exception as exc:  # noqa: BLE001
            raise SearchStoreUnavailableError(str(exc)) from exc
        logger.info(
            "retrieval_v2_qdrant_upsert %s",
            RetrievalV2Trace(
                operation_id=new_operation_id(),
                tenant_id=tid,
                operation="upsert",
                dimensions=dims,
                duration_ms=timer.ms(),
                status="ok",
                extra={"count": len(point_ids), "collection": self._collection},
            ).to_dict(),
        )
        return point_ids

    async def delete_documents(self, *, tenant_id: str, point_ids: list[str]) -> int:
        tid = _require_tenant(tenant_id)
        ids = [p for p in point_ids if (p or "").strip()]
        if not ids:
            return 0
        client = self._get_client()
        from qdrant_client.http import models as qm

        try:
            client.delete(
                collection_name=self._collection,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tid)),
                            qm.HasIdCondition(has_id=ids),
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise SearchStoreUnavailableError(str(exc)) from exc
        return len(ids)

    async def deactivate_documents(self, *, tenant_id: str, point_ids: list[str]) -> int:
        tid = _require_tenant(tenant_id)
        ids = [p for p in point_ids if (p or "").strip()]
        if not ids:
            return 0
        client = self._get_client()
        from qdrant_client.http import models as qm

        try:
            client.set_payload(
                collection_name=self._collection,
                payload={"active": False},
                points=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tid)),
                            qm.HasIdCondition(has_id=ids),
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise SearchStoreUnavailableError(str(exc)) from exc
        return len(ids)

    async def search_dense(
        self,
        *,
        tenant_id: str,
        query_vector: list[float],
        limit: int = 10,
        source_types: list[str] | None = None,
        active_only: bool = True,
    ) -> list[DenseSearchHit]:
        tid = _require_tenant(tenant_id)
        if not query_vector:
            raise RetrievalV2ValidationError("query_vector is required")
        client = self._get_client()
        from qdrant_client.http import models as qm

        must: list[Any] = [qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tid))]
        if active_only:
            must.append(qm.FieldCondition(key="active", match=qm.MatchValue(value=True)))
        if source_types:
            must.append(qm.FieldCondition(key="source_type", match=qm.MatchAny(any=list(source_types))))

        timer = TraceTimer()
        try:
            if hasattr(client, "query_points"):
                raw = client.query_points(
                    collection_name=self._collection,
                    query=list(query_vector),
                    query_filter=qm.Filter(must=must),
                    limit=max(1, int(limit)),
                    with_payload=True,
                )
                points = getattr(raw, "points", raw)
            else:
                points = client.search(
                    collection_name=self._collection,
                    query_vector=list(query_vector),
                    query_filter=qm.Filter(must=must),
                    limit=max(1, int(limit)),
                    with_payload=True,
                )
        except Exception as exc:  # noqa: BLE001
            raise SearchStoreUnavailableError(str(exc)) from exc

        hits: list[DenseSearchHit] = []
        for point in points or []:
            payload = dict(getattr(point, "payload", None) or {})
            if str(payload.get("tenant_id") or "") != tid:
                continue
            try:
                doc = self._document_from_payload(payload)
            except Exception:
                continue
            hits.append(
                DenseSearchHit(
                    point_id=str(getattr(point, "id", doc.point_id)),
                    score=float(getattr(point, "score", 0.0) or 0.0),
                    document=doc,
                )
            )
        logger.info(
            "retrieval_v2_qdrant_search %s",
            RetrievalV2Trace(
                operation_id=new_operation_id(),
                tenant_id=tid,
                operation="search_dense",
                duration_ms=timer.ms(),
                status="ok",
                extra={"hit_count": len(hits), "limit": limit},
            ).to_dict(),
        )
        return hits

    def _document_from_payload(self, payload: dict[str, Any]) -> SearchDocument:
        return SearchDocument(
            tenant_id=str(payload.get("tenant_id") or ""),
            source_type=SourceType(str(payload.get("source_type"))),
            source_id=str(payload.get("source_id") or ""),
            chunk_id=str(payload.get("chunk_id") or ""),
            semantic_text=str(payload.get("semantic_text") or ""),
            title=str(payload.get("title") or ""),
            parent_id=str(payload.get("parent_id") or ""),
            keywords=tuple(payload.get("keywords") or ()),
            aliases=tuple(payload.get("aliases") or ()),
            language_hints=tuple(payload.get("language_hints") or ()),
            active=bool(payload.get("active", True)),
            published_revision=str(payload.get("published_revision") or ""),
            source_version=str(payload.get("source_version") or ""),
            content_sha256=str(payload.get("content_sha256") or ""),
            embedding_model=str(payload.get("embedding_model") or ""),
            embedding_dimensions=int(payload.get("embedding_dimensions") or 0),
            updated_at=str(payload.get("updated_at") or ""),
            priority=int(payload.get("priority") or 0),
            metadata=dict(payload.get("metadata") or {}),
            index_schema_version=str(payload.get("index_schema_version") or ""),
        )

    async def health_check(self) -> dict[str, object]:
        try:
            client = self._get_client()
            exists = self._collection_exists(client)
            dims = None
            if exists:
                dims = self._read_vector_size(client.get_collection(self._collection))
            return {
                "status": "ok" if exists else "missing_collection",
                "collection": self._collection,
                "exists": exists,
                "dimensions": dims,
                "distance": DENSE_DISTANCE,
            }
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc), "collection": self._collection}
