"""Rerank fused candidates with rerank-2.5. Skip exact lookups. Failures keep fused order."""

from __future__ import annotations

import os

from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.config import rerank_model
from services.customer_ai.providers.voyage_client import rerank_texts
from services.customer_ai.retrieve.hybrid import HybridHit


def rerank_enabled() -> bool:
    raw = (os.getenv("CUSTOMER_BRAIN_RERANK") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def should_rerank(hits: list[HybridHit]) -> bool:
    if not rerank_enabled() or len(hits) <= 1:
        return False
    top = hits[0]
    if top.lexical_score >= 0.85 and all(item.card.item_id != top.card.item_id or i == 0 for i, item in enumerate(hits[:1])):
        if top.lexical_score >= 0.99:
            return False
    return True


async def rerank_hits(query: str, hits: list[HybridHit], *, tenant_id: str = "") -> list[HybridHit]:
    if not hits or not should_rerank(hits) or not voyage_configured():
        return hits
    documents = [item.card.search_text for item in hits]
    try:
        ranked = await rerank_texts(query=query, documents=documents, model=rerank_model())
        if tenant_id.strip():
            from datetime import datetime, timezone

            from services.membership.provider_expense import record_pending_provider

            record_pending_provider(
                event_id=f"rerank:{tenant_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
                tenant_id=tenant_id,
                category="rerank",
                feature="knowledge",
                provider="voyage",
                model=rerank_model(),
                quantity=len(documents),
            )
    except Exception:
        return hits
    if not ranked:
        return hits
    out: list[HybridHit] = []
    seen: set[str] = set()
    for row in ranked:
        if row.index < 0 or row.index >= len(hits):
            continue
        hit = hits[row.index]
        if hit.card.item_id in seen:
            continue
        seen.add(hit.card.item_id)
        out.append(
            HybridHit(
                card=hit.card,
                lexical_score=hit.lexical_score,
                semantic_score=hit.semantic_score,
                fused_rank=len(out),
            )
        )
    for hit in hits:
        if hit.card.item_id not in seen:
            out.append(hit)
    return out
