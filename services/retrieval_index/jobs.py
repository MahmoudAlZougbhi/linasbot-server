"""Index job schema for Retrieval V2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from services.retrieval_v2.errors import RetrievalV2ValidationError, SearchTenantRequiredError
from services.retrieval_v2.schemas import SourceType


class IndexOperation(str, Enum):
    UPSERT = "UPSERT"
    DEACTIVATE = "DEACTIVATE"
    DELETE = "DELETE"


@dataclass(frozen=True)
class IndexJob:
    tenant_id: str
    source_type: SourceType
    source_id: str
    source_version: str
    published_revision: str
    operation: IndexOperation
    content_checksum: str
    chunk_id: str = "main"
    point_id: str = ""

    def __post_init__(self) -> None:
        tid = (self.tenant_id or "").strip()
        if not tid:
            raise SearchTenantRequiredError("tenant_id is required on IndexJob")
        object.__setattr__(self, "tenant_id", tid)
        if not (self.source_id or "").strip():
            raise RetrievalV2ValidationError("source_id is required on IndexJob")
        if not isinstance(self.operation, IndexOperation):
            object.__setattr__(self, "operation", IndexOperation(str(self.operation)))
        if not isinstance(self.source_type, SourceType):
            object.__setattr__(self, "source_type", SourceType(str(self.source_type)))
