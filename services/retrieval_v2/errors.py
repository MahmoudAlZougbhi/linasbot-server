"""Typed errors for Retrieval V2 providers and stores."""

from __future__ import annotations


class RetrievalV2Error(Exception):
    """Base Retrieval V2 error."""


class RetrievalV2ConfigError(RetrievalV2Error):
    """Missing or invalid configuration."""


class RetrievalV2ValidationError(RetrievalV2Error):
    """Invalid SearchDocument or search request."""


class EmbeddingRateLimitedError(RetrievalV2Error):
    """Provider returned 429 / rate limit."""


class EmbeddingUnavailableError(RetrievalV2Error):
    """Provider timeout, 5xx, or network failure after retries."""


class EmbeddingInvalidResponseError(RetrievalV2Error):
    """Provider returned malformed or wrong-dimension vectors."""


class SearchStoreUnavailableError(RetrievalV2Error):
    """Qdrant (or other store) unreachable."""


class SearchStoreConfigError(RetrievalV2Error):
    """Collection missing or incompatible (e.g. wrong vector size)."""


class SearchTenantRequiredError(RetrievalV2ValidationError):
    """tenant_id is mandatory on every search / mutate call."""
