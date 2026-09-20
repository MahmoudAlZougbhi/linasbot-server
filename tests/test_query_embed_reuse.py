"""P2: one query embedding per tenant+space+query until publish invalidates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.brain.retrieve import query_embed


@pytest.mark.asyncio
async def test_same_query_reused_within_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    query_embed.invalidate_query_embeds()
    query_embed.EMBED_CALLS = 0
    calls = {"n": 0}

    async def fake_embed_texts(_space: object, _texts: list[str]) -> SimpleNamespace:
        calls["n"] += 1
        return SimpleNamespace(vectors=[[0.1, 0.2, 0.3]])

    monkeypatch.setattr("services.brain.providers.voyage_client.embed_texts", fake_embed_texts)
    space = SimpleNamespace(space_id="entity_query", model="voyage", endpoint="query")
    first, _ = await query_embed.embed_query_vector(space, "hours?", tenant_id="t1")
    second, _ = await query_embed.embed_query_vector(space, "hours?", tenant_id="t1")
    assert first == second
    assert query_embed.EMBED_CALLS == 1
    assert calls["n"] == 1
    await query_embed.embed_query_vector(space, "hours?", tenant_id="t2")
    assert query_embed.EMBED_CALLS == 2
    assert calls["n"] == 2
