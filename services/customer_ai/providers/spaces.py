"""Immutable embedding-space contracts. Never mix spaces by dimension alone.

Production Customer Brain retrieval:
- ENTITY (`voyage-4-large`) for services/products/branches/hours
- KNOWLEDGE (`voyage-context-4`) contextual embeddings for knowledge/care/faq
"""

from __future__ import annotations

from dataclasses import dataclass

from services.customer_ai.budgets import DEFAULT_BUDGETS

PROVIDER = "voyage"
KNOWLEDGE_MODEL = "voyage-context-4"
ENTITY_MODEL = "voyage-4-large"
MULTIMODAL_MODEL = "voyage-multimodal-3.5"
RERANK_MODEL = "rerank-2.5"
RERANK_CANDIDATE = "rerank-3"
DISTANCE = "cosine"
PREPROCESS_VERSION = "v1"


@dataclass(frozen=True)
class EmbeddingSpace:
    space_id: str
    provider: str
    model: str
    endpoint: str
    dimensions: int
    data_type: str
    distance: str
    preprocess_version: str
    input_mode: str


def _space(*, family: str, model: str, endpoint: str, input_mode: str) -> EmbeddingSpace:
    dims = DEFAULT_BUDGETS.embedding_dimensions
    space_id = "|".join(
        (PROVIDER, model, endpoint, str(dims), "fp32", DISTANCE, PREPROCESS_VERSION, input_mode)
    )
    return EmbeddingSpace(
        space_id=space_id,
        provider=PROVIDER,
        model=model,
        endpoint=endpoint,
        dimensions=dims,
        data_type="fp32",
        distance=DISTANCE,
        preprocess_version=PREPROCESS_VERSION,
        input_mode=input_mode,
    )


KNOWLEDGE_DOCUMENT = _space(
    family="knowledge",
    model=KNOWLEDGE_MODEL,
    endpoint="contextualized",
    input_mode="document",
)
KNOWLEDGE_QUERY = _space(
    family="knowledge",
    model=KNOWLEDGE_MODEL,
    endpoint="contextualized",
    input_mode="query",
)
ENTITY_DOCUMENT = _space(
    family="entity",
    model=ENTITY_MODEL,
    endpoint="embeddings",
    input_mode="document",
)
ENTITY_QUERY = _space(
    family="entity",
    model=ENTITY_MODEL,
    endpoint="embeddings",
    input_mode="query",
)
MULTIMODAL_DOCUMENT = _space(
    family="multimodal",
    model=MULTIMODAL_MODEL,
    endpoint="multimodal",
    input_mode="document",
)
MULTIMODAL_QUERY = _space(
    family="multimodal",
    model=MULTIMODAL_MODEL,
    endpoint="multimodal",
    input_mode="query",
)


def compatible(index: EmbeddingSpace, query: EmbeddingSpace) -> bool:
    return (
        index.provider == query.provider
        and index.model == query.model
        and index.endpoint == query.endpoint
        and index.dimensions == query.dimensions
        and index.data_type == query.data_type
        and index.distance == query.distance
        and index.preprocess_version == query.preprocess_version
        and index.input_mode == "document"
        and query.input_mode == "query"
    )


def spaces_snapshot() -> dict[str, str]:
    return {
        "entity_document": ENTITY_DOCUMENT.space_id,
        "knowledge_document": KNOWLEDGE_DOCUMENT.space_id,
        "knowledge_model": KNOWLEDGE_MODEL,
        "entity_model": ENTITY_MODEL,
        "multimodal_document": MULTIMODAL_DOCUMENT.space_id,
        "rerank": RERANK_MODEL,
        "rerank_preview_gated": RERANK_CANDIDATE,
        "contextual_active": "true",
    }
