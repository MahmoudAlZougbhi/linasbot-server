"""Voyage client fails closed without credentials."""

from __future__ import annotations

import pytest

from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.brain.providers.voyage_client import (
    QUERY_ATTEMPTS,
    QUERY_TIMEOUT_SECONDS,
    VoyageNotConfiguredError,
    embed_texts,
)


@pytest.mark.asyncio
async def test_voyage_embed_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    with pytest.raises(VoyageNotConfiguredError):
        await embed_texts(ENTITY_DOCUMENT, ["hair removal"])


def test_voyage_query_budget_retries_rate_limits() -> None:
    assert QUERY_TIMEOUT_SECONDS <= 12.0
    assert QUERY_ATTEMPTS >= 4
    assert QUERY_ATTEMPTS <= 6
