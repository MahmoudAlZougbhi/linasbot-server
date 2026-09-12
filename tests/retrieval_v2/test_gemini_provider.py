"""Gemini embedding provider unit tests (mocked — no live API)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services.retrieval_v2.errors import (
    EmbeddingInvalidResponseError,
    EmbeddingRateLimitedError,
    EmbeddingUnavailableError,
    RetrievalV2ConfigError,
    RetrievalV2ValidationError,
)
from services.retrieval_v2.providers.gemini_embeddings import (
    GeminiEmbeddingProvider,
    format_document_for_embedding,
    format_query_for_embedding,
)


def test_query_and_document_prefixes() -> None:
    assert format_query_for_embedding("hello") == "task: search result | query: hello"
    assert format_document_for_embedding("body", title="T") == "title: T | text: body"
    with pytest.raises(RetrievalV2ValidationError):
        format_query_for_embedding(" ")


class _FakeModels:
    def __init__(self, behavior: Any) -> None:
        self.behavior = behavior
        self.calls: list[dict[str, Any]] = []

    def embed_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.behavior(kwargs)


class _FakeClient:
    def __init__(self, behavior: Any) -> None:
        self.models = _FakeModels(behavior)


def _vec(n: int, fill: float = 0.1) -> list[float]:
    return [fill] * n


@pytest.mark.asyncio
async def test_embed_query_dimension_and_payload() -> None:
    dims = 128

    def behavior(kwargs: dict[str, Any]) -> Any:
        assert kwargs["model"] == "gemini-embedding-2"
        assert kwargs["contents"] == ["task: search result | query: laser price"]
        cfg = kwargs["config"]
        assert cfg.output_dimensionality == dims
        # task_type must NOT be set for gemini-embedding-2
        assert getattr(cfg, "task_type", None) in (None, "")
        return SimpleNamespace(embeddings=[SimpleNamespace(values=_vec(dims))])

    provider = GeminiEmbeddingProvider(
        api_key="test-key",
        model="gemini-embedding-2",
        dimensions=dims,
        client_factory=lambda: _FakeClient(behavior),
    )
    vec = await provider.embed_query("laser price")
    assert len(vec) == dims


@pytest.mark.asyncio
async def test_embed_documents_batch() -> None:
    dims = 128

    def behavior(kwargs: dict[str, Any]) -> Any:
        contents = kwargs["contents"]
        assert contents[0].startswith("title:")
        return SimpleNamespace(embeddings=[SimpleNamespace(values=_vec(dims, 0.2)) for _ in contents])

    provider = GeminiEmbeddingProvider(
        api_key="test-key",
        dimensions=dims,
        max_batch=2,
        client_factory=lambda: _FakeClient(behavior),
    )
    vectors = await provider.embed_documents(["a", "b", "c"], titles=["t1", "t2", "t3"])
    assert len(vectors) == 3
    assert all(len(v) == dims for v in vectors)


@pytest.mark.asyncio
async def test_empty_input_rejected() -> None:
    provider = GeminiEmbeddingProvider(api_key="k", dimensions=128, client_factory=lambda: _FakeClient(lambda _: None))
    with pytest.raises(RetrievalV2ValidationError):
        await provider.embed_query(" ")
    with pytest.raises(RetrievalV2ValidationError):
        await provider.embed_documents(["ok", " "])


@pytest.mark.asyncio
async def test_429_retries_then_rate_limited() -> None:
    attempts = {"n": 0}

    def behavior(_kwargs: dict[str, Any]) -> Any:
        attempts["n"] += 1
        raise RuntimeError("429 rate limit exceeded")

    provider = GeminiEmbeddingProvider(
        api_key="k",
        dimensions=128,
        max_attempts=3,
        timeout_seconds=5,
        client_factory=lambda: _FakeClient(behavior),
    )
    with pytest.raises(EmbeddingRateLimitedError):
        await provider.embed_query("x")
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_timeout_becomes_unavailable() -> None:
    def behavior(_kwargs: dict[str, Any]) -> Any:
        raise TimeoutError("timed out")

    provider = GeminiEmbeddingProvider(
        api_key="k",
        dimensions=128,
        max_attempts=2,
        client_factory=lambda: _FakeClient(behavior),
    )
    with pytest.raises(EmbeddingUnavailableError):
        await provider.embed_query("x")


@pytest.mark.asyncio
async def test_invalid_dimension_response() -> None:
    def behavior(_kwargs: dict[str, Any]) -> Any:
        return SimpleNamespace(embeddings=[SimpleNamespace(values=_vec(64))])

    provider = GeminiEmbeddingProvider(
        api_key="k",
        dimensions=128,
        max_attempts=1,
        client_factory=lambda: _FakeClient(behavior),
    )
    with pytest.raises(EmbeddingInvalidResponseError):
        await provider.embed_query("x")


def test_missing_api_key_config_error() -> None:
    provider = GeminiEmbeddingProvider(api_key="", dimensions=128)
    with pytest.raises(RetrievalV2ConfigError):
        provider._require_key()


def test_configured_dimensions_bounds() -> None:
    with pytest.raises(RetrievalV2ConfigError):
        GeminiEmbeddingProvider(api_key="k", dimensions=10_000)
    with pytest.raises(RetrievalV2ConfigError):
        GeminiEmbeddingProvider(api_key="k", dimensions=64)
