"""Index/content version metadata for fail-closed freshness checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndexVersions:
    content_version: str
    index_version: str
    embedding_model: str
    chunker_version: str
    retrieval_schema_version: str
    built_at: str = ""


RETRIEVAL_SCHEMA_VERSION = "customer_ai.retrieve.v2"
CHUNKER_VERSION = "customer_ai.chunk.v1"


def versions_match(content_version: str, index_version: str) -> bool:
    left = (content_version or "").strip()
    right = (index_version or "").strip()
    return bool(left) and left == right


def freshness_gate(*, content_version: str, index_version: str) -> dict[str, Any]:
    ok = versions_match(content_version, index_version)
    return {
        "ok": ok,
        "content_version": content_version,
        "index_version": index_version,
        "reason": "ok" if ok else "content_index_version_mismatch",
        "retrieval_schema_version": RETRIEVAL_SCHEMA_VERSION,
        "chunker_version": CHUNKER_VERSION,
    }
