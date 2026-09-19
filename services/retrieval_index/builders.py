"""Document builder contract — concrete builders come in later phases."""

from __future__ import annotations

from typing import Protocol

from services.retrieval_v2.schemas import SearchDocument, SourceType


class SearchDocumentBuilder(Protocol):
    """Builds SearchDocument rows for a source. Not connected to CM yet."""

    source_type: SourceType

    def build(self, *, tenant_id: str, source_id: str, payload: dict) -> list[SearchDocument]:
        """Return zero or more searchable documents for one source entity."""
        ...
