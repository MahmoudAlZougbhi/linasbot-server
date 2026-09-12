"""Deterministic fake embeddings for unit/integration tests (no external calls)."""

from __future__ import annotations

import hashlib
import math

from services.retrieval_v2.errors import RetrievalV2ValidationError


class FakeEmbeddingProvider:
    def __init__(self, *, dimensions: int = 32, model_id: str = "fake-embed") -> None:
        if dimensions < 8:
            raise ValueError("dimensions too small")
        self._dimensions = dimensions
        self._model_id = model_id

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def health_check(self) -> dict[str, object]:
        return {"provider": self.provider_name, "model": self.model_id, "dimensions": self.dimensions, "status": "ok"}

    async def embed_query(self, text: str) -> list[float]:
        if not (text or "").strip():
            raise RetrievalV2ValidationError("query text is empty")
        return self._vector(text)

    async def embed_documents(self, texts: list[str], *, titles: list[str] | None = None) -> list[list[float]]:
        if titles is not None and len(titles) != len(texts):
            raise RetrievalV2ValidationError("titles length must match texts length")
        out: list[list[float]] = []
        for i, text in enumerate(texts):
            if not (text or "").strip():
                raise RetrievalV2ValidationError("document text is empty")
            title = titles[i] if titles else ""
            out.append(self._vector(f"{title}\n{text}"))
        return out

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw: list[float] = []
        while len(raw) < self._dimensions:
            for b in digest:
                raw.append((b / 255.0) * 2.0 - 1.0)
                if len(raw) >= self._dimensions:
                    break
            digest = hashlib.sha256(digest).digest()
        # L2 normalize for cosine-friendly tests
        norm = math.sqrt(sum(v * v for v in raw)) or 1.0
        return [v / norm for v in raw]
