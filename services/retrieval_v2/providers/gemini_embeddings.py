"""Gemini Embedding 2 provider (google-genai SDK).

Official model id: gemini-embedding-2
task_type parameter is NOT used for gemini-embedding-2 — Google recommends
prompt prefixes instead (search query vs document).
Default dimensions: 3072 (highest quality; configurable via env).
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

from services.retrieval_v2.config import (
    gemini_api_key,
    gemini_embedding_dimensions,
    gemini_embedding_max_attempts,
    gemini_embedding_max_batch,
    gemini_embedding_model,
    gemini_embedding_timeout_seconds,
)
from services.retrieval_v2.errors import (
    EmbeddingInvalidResponseError,
    EmbeddingRateLimitedError,
    EmbeddingUnavailableError,
    RetrievalV2ConfigError,
    RetrievalV2ValidationError,
)
from services.retrieval_v2.trace import RetrievalV2Trace, TraceTimer, new_operation_id

logger = logging.getLogger(__name__)


def format_query_for_embedding(text: str) -> str:
    """Asymmetric retrieval query prefix (Gemini Embedding 2 docs)."""
    body = (text or "").strip()
    if not body:
        raise RetrievalV2ValidationError("query text is empty")
    return f"task: search result | query: {body}"


def format_document_for_embedding(text: str, *, title: str = "") -> str:
    """Asymmetric retrieval document prefix (Gemini Embedding 2 docs)."""
    body = (text or "").strip()
    if not body:
        raise RetrievalV2ValidationError("document text is empty")
    t = (title or "").strip()
    if t:
        return f"title: {t} | text: {body}"
    return f"title: | text: {body}"


def _is_rate_limit(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg:
        return True
    if "ratelimit" in name or "rate_limit" in name:
        return True
    return "rate" in msg and "limit" in msg


def _is_retryable(exc: BaseException) -> bool:
    if _is_rate_limit(exc):
        return True
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if any(tok in msg for tok in ("500", "502", "503", "504", "unavailable", "timeout", "timed out")):
        return True
    return "timeout" in name or "unavailable" in name


class GeminiEmbeddingProvider:
    """Dense embeddings via google.genai Client.models.embed_content."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout_seconds: float | None = None,
        max_batch: int | None = None,
        max_attempts: int | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else gemini_api_key()).strip()
        self._model = (model or gemini_embedding_model()).strip()
        self._dimensions = int(dimensions if dimensions is not None else gemini_embedding_dimensions())
        self._timeout = float(timeout_seconds if timeout_seconds is not None else gemini_embedding_timeout_seconds())
        self._max_batch = int(max_batch if max_batch is not None else gemini_embedding_max_batch())
        self._max_attempts = int(max_attempts if max_attempts is not None else gemini_embedding_max_attempts())
        self._client_factory = client_factory
        self._client: Any | None = None
        if self._dimensions < 128 or self._dimensions > 3072:
            raise RetrievalV2ConfigError("GEMINI_EMBEDDING_DIMENSIONS must be between 128 and 3072")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _require_key(self) -> None:
        if not self._api_key:
            raise RetrievalV2ConfigError("GEMINI_API_KEY (or GOOGLE_API_KEY) is required for Gemini embeddings")

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        self._require_key()
        try:
            from google import genai
        except ImportError as exc:
            raise RetrievalV2ConfigError("google-genai package is required for GeminiEmbeddingProvider") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def health_check(self) -> dict[str, object]:
        ok_import = True
        try:
            import google.genai  # noqa: F401
        except ImportError:
            ok_import = False
        return {
            "provider": self.provider_name,
            "model": self.model_id,
            "dimensions": self.dimensions,
            "api_key_configured": bool(self._api_key),
            "sdk_import_ok": ok_import,
            "status": "ok" if ok_import and bool(self._api_key) else "degraded",
        }

    async def embed_query(self, text: str) -> list[float]:
        formatted = format_query_for_embedding(text)
        vectors = await self._embed_raw([formatted], operation="embed_query")
        return vectors[0]

    async def embed_documents(self, texts: list[str], *, titles: list[str] | None = None) -> list[list[float]]:
        if not texts:
            return []
        if titles is not None and len(titles) != len(texts):
            raise RetrievalV2ValidationError("titles length must match texts length")
        formatted: list[str] = []
        for i, body in enumerate(texts):
            title = titles[i] if titles else ""
            formatted.append(format_document_for_embedding(body, title=title))
        out: list[list[float]] = []
        for start in range(0, len(formatted), self._max_batch):
            chunk = formatted[start : start + self._max_batch]
            out.extend(await self._embed_raw(chunk, operation="embed_documents"))
        return out

    async def _embed_raw(self, contents: list[str], *, operation: str) -> list[list[float]]:
        if not contents:
            return []
        if any(not (c or "").strip() for c in contents):
            raise RetrievalV2ValidationError("embedding contents must be non-empty")
        timer = TraceTimer()
        retries = 0
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                vectors = await asyncio.wait_for(self._call_embed(contents), timeout=self._timeout)
                self._validate_vectors(vectors, expected=len(contents))
                logger.info(
                    "retrieval_v2_embed %s",
                    RetrievalV2Trace(
                        operation_id=new_operation_id(),
                        tenant_id="",
                        operation=operation,
                        provider=self.provider_name,
                        model=self.model_id,
                        dimensions=self.dimensions,
                        duration_ms=timer.ms(),
                        retry_count=retries,
                        status="ok",
                        extra={"batch_size": len(contents)},
                    ).to_dict(),
                )
                return vectors
            except EmbeddingInvalidResponseError:
                raise
            except RetrievalV2ValidationError:
                raise
            except RetrievalV2ConfigError:
                raise
            except Exception as exc:  # noqa: BLE001 — classified below
                last_exc = exc
                if _is_rate_limit(exc):
                    retries += 1
                    if attempt >= self._max_attempts:
                        raise EmbeddingRateLimitedError(str(exc)) from exc
                elif _is_retryable(exc):
                    retries += 1
                    if attempt >= self._max_attempts:
                        raise EmbeddingUnavailableError(str(exc)) from exc
                else:
                    raise EmbeddingUnavailableError(str(exc)) from exc
                delay = min(8.0, (2 ** (attempt - 1)) * 0.25) + random.uniform(0, 0.25)
                await asyncio.sleep(delay)
        raise EmbeddingUnavailableError(str(last_exc) if last_exc else "embed failed")

    async def _call_embed(self, contents: list[str]) -> list[list[float]]:
        client = self._get_client()

        def _sync() -> list[list[float]]:
            from google.genai import types

            response = client.models.embed_content(
                model=self._model,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
            )
            embeddings = getattr(response, "embeddings", None) or []
            vectors: list[list[float]] = []
            for item in embeddings:
                values = getattr(item, "values", None)
                if values is None and isinstance(item, dict):
                    values = item.get("values")
                if not values:
                    raise EmbeddingInvalidResponseError("missing embedding values")
                vectors.append([float(v) for v in values])
            return vectors

        return await asyncio.to_thread(_sync)

    def _validate_vectors(self, vectors: list[list[float]], *, expected: int) -> None:
        if len(vectors) != expected:
            raise EmbeddingInvalidResponseError(f"expected {expected} vectors, got {len(vectors)}")
        for vec in vectors:
            if len(vec) != self._dimensions:
                raise EmbeddingInvalidResponseError(f"expected dimension {self._dimensions}, got {len(vec)}")
