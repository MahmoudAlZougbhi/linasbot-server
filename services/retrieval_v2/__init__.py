"""Customer Knowledge & Retrieval V2 — foundations (Phase 0/1).

Isolated from live Customer Reply V2. Flags default OFF. No cutover wiring.
"""

from __future__ import annotations

from services.retrieval_v2.config import INDEX_SCHEMA_VERSION, retrieval_v2_enabled, retrieval_v2_shadow_enabled
from services.retrieval_v2.schemas import SearchDocument, SourceType, document_point_id

__all__ = [
    "INDEX_SCHEMA_VERSION",
    "SearchDocument",
    "SourceType",
    "document_point_id",
    "retrieval_v2_enabled",
    "retrieval_v2_shadow_enabled",
]
