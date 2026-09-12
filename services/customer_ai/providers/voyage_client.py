"""Voyage HTTP client. Missing key is provider_not_configured — never a fake embed."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.flags import voyage_api_key
from services.customer_ai.providers.spaces import EmbeddingSpace

VOYAGE_BASE = "https://api.voyageai.com/v1"
_RETRY_STATUSES = {429, 502, 503, 504}


class VoyageNotConfiguredError(RuntimeError):
    code = "provider_not_configured"


class VoyageContractError(RuntimeError):
    code = "provider_error"


@dataclass(frozen=True)
class VoyageVectors:
    space_id: str
    vectors: list[list[float]]


def _headers() -> dict[str, str]:
    key = voyage_api_key()
    if not key:
        raise VoyageNotConfiguredError("VOYAGE_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _validate(space: EmbeddingSpace, vectors: list[list[float]]) -> None:
    if not vectors:
        raise VoyageContractError("empty_embedding_response")
    for row in vectors:
        if len(row) != space.dimensions:
            raise VoyageContractError(f"dimension_mismatch:{len(row)}!={space.dimensions}")
        if not all(isinstance(v, (int, float)) and v == v and v not in {float("inf"), float("-inf")} for v in row):
            raise VoyageContractError("non_finite_embedding")


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    raw = (response.headers.get("Retry-After") or "").strip()
    if raw.isdigit():
        return min(float(raw), 45.0)
    return float(min(1.5 * (2**attempt), 30.0))


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = _headers()
    async with httpx.AsyncClient(timeout=90.0) as client:
        response: httpx.Response | None = None
        for attempt in range(8):
            response = await client.post(f"{VOYAGE_BASE}{path}", headers=headers, json=payload)
            if response.status_code in _RETRY_STATUSES and attempt < 7:
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            break
    assert response is not None
    if response.status_code >= 400:
        raise VoyageContractError(f"http_{response.status_code}")
    data = response.json()
    if not isinstance(data, dict):
        raise VoyageContractError("invalid_json")
    return data


async def embed_texts(space: EmbeddingSpace, texts: list[str]) -> VoyageVectors:
    if space.endpoint != "embeddings":
        raise VoyageContractError(f"wrong_endpoint:{space.endpoint}")
    payload: dict[str, Any] = {
        "model": space.model,
        "input": texts,
        "input_type": space.input_mode,
        "output_dimension": space.dimensions,
    }
    data = await _post("/embeddings", payload)
    vectors = [list(item.get("embedding") or []) for item in data.get("data") or []]
    _validate(space, vectors)
    return VoyageVectors(space_id=space.space_id, vectors=vectors)


async def embed_contextual_groups(space: EmbeddingSpace, groups: list[list[str]]) -> list[VoyageVectors]:
    if space.endpoint != "contextualized":
        raise VoyageContractError(f"wrong_endpoint:{space.endpoint}")
    payload: dict[str, Any] = {
        "model": space.model,
        "inputs": groups,
        "input_type": space.input_mode,
        "output_dimension": space.dimensions,
    }
    data = await _post("/contextualizedembeddings", payload)
    out: list[VoyageVectors] = []
    for group in data.get("data") or []:
        rows = group.get("data") if isinstance(group, dict) else None
        vectors = [list(item.get("embedding") or []) for item in rows or []]
        _validate(space, vectors)
        out.append(VoyageVectors(space_id=space.space_id, vectors=vectors))
    if len(out) != len(groups):
        raise VoyageContractError("contextual_group_mismatch")
    return out


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float


async def rerank_texts(*, query: str, documents: list[str], model: str, top_k: int | None = None) -> list[RerankHit]:
    payload: dict[str, Any] = {"query": query, "documents": documents, "model": model}
    if top_k is not None:
        payload["top_k"] = top_k
    data = await _post("/rerank", payload)
    hits: list[RerankHit] = []
    for item in data.get("data") or data.get("results") or []:
        if not isinstance(item, dict):
            continue
        hits.append(RerankHit(index=int(item.get("index") or 0), score=float(item.get("relevance_score") or 0.0)))
    hits.sort(key=lambda row: -row.score)
    return hits


def default_dimensions() -> int:
    return DEFAULT_BUDGETS.embedding_dimensions
