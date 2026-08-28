"""SearchDocument schema and deterministic point IDs for Retrieval V2."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from services.retrieval_v2.config import INDEX_SCHEMA_VERSION
from services.retrieval_v2.errors import RetrievalV2ValidationError


class SourceType(StrEnum):
    KNOWLEDGE = "knowledge"
    CARE = "care"
    FAQ = "faq"
    SERVICE = "service"
    PRICE_CATALOG = "price_catalog"
    PRODUCT = "product"
    BRANCH = "branch"
    POLICY = "policy"
    REQUEST_DEFINITION = "request_definition"
    COMMENT_GUIDANCE = "comment_guidance"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_point_id(
    *,
    tenant_id: str,
    source_type: SourceType | str,
    source_id: str,
    chunk_id: str,
    index_schema_version: str = INDEX_SCHEMA_VERSION,
) -> str:
    """Deterministic Qdrant point id (UUID derived from identity; stable upsert key)."""
    st = source_type.value if isinstance(source_type, SourceType) else str(source_type)
    raw = "|".join(
        [
            (tenant_id or "").strip(),
            st.strip(),
            (source_id or "").strip(),
            (chunk_id or "").strip(),
            (index_schema_version or "").strip(),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Qdrant accepts UUID or unsigned int — format first 32 hex chars as UUID.
    h = digest[:32]
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _require_non_empty(name: str, value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise RetrievalV2ValidationError(f"{name} is required")
    return text


@dataclass(frozen=True)
class SearchDocument:
    """Unified searchable unit. Vectors attach to this identity, not to raw CM rows."""

    tenant_id: str
    source_type: SourceType
    source_id: str
    chunk_id: str
    semantic_text: str
    title: str = ""
    parent_id: str = ""
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    language_hints: tuple[str, ...] = ()
    active: bool = True
    published_revision: str = ""
    source_version: str = ""
    content_sha256: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 0
    updated_at: str = ""
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    index_schema_version: str = INDEX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _require_non_empty("tenant_id", self.tenant_id))
        object.__setattr__(self, "source_id", _require_non_empty("source_id", self.source_id))
        object.__setattr__(self, "chunk_id", _require_non_empty("chunk_id", self.chunk_id))
        if not isinstance(self.source_type, SourceType):
            object.__setattr__(self, "source_type", SourceType(str(self.source_type)))
        text = (self.semantic_text or "").strip()
        if not text:
            raise RetrievalV2ValidationError("semantic_text is required")
        object.__setattr__(self, "semantic_text", text)
        if not (self.content_sha256 or "").strip():
            object.__setattr__(self, "content_sha256", content_sha256(text))
        if not (self.updated_at or "").strip():
            object.__setattr__(self, "updated_at", utc_now_iso())
        if not (self.index_schema_version or "").strip():
            object.__setattr__(self, "index_schema_version", INDEX_SCHEMA_VERSION)

    @property
    def point_id(self) -> str:
        return document_point_id(
            tenant_id=self.tenant_id,
            source_type=self.source_type,
            source_id=self.source_id,
            chunk_id=self.chunk_id,
            index_schema_version=self.index_schema_version,
        )

    def with_embedding_meta(self, *, model: str, dimensions: int) -> SearchDocument:
        return SearchDocument(
            tenant_id=self.tenant_id,
            source_type=self.source_type,
            source_id=self.source_id,
            chunk_id=self.chunk_id,
            semantic_text=self.semantic_text,
            title=self.title,
            parent_id=self.parent_id,
            keywords=self.keywords,
            aliases=self.aliases,
            language_hints=self.language_hints,
            active=self.active,
            published_revision=self.published_revision,
            source_version=self.source_version,
            content_sha256=self.content_sha256,
            embedding_model=model,
            embedding_dimensions=dimensions,
            updated_at=self.updated_at,
            priority=self.priority,
            metadata=dict(self.metadata),
            index_schema_version=self.index_schema_version,
        )

    def to_payload(self) -> dict[str, Any]:
        """Qdrant payload — never includes the embedding vector."""
        data = asdict(self)
        data["source_type"] = self.source_type.value
        data["keywords"] = list(self.keywords)
        data["aliases"] = list(self.aliases)
        data["language_hints"] = list(self.language_hints)
        # Keep semantic_text in payload for debugging/hydration hints; callers may redact in logs.
        return data


@dataclass(frozen=True)
class DenseSearchHit:
    point_id: str
    score: float
    document: SearchDocument
