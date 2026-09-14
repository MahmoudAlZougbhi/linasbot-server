"""FAQ/knowledge semantic search via Customer Brain Voyage retrieve.

Live CM publish does not build a second OpenAI file index. This wrapper maps
Brain evidence into the old runtime_pipeline hit shape.
"""

from __future__ import annotations

from typing import Any

_FAQ_SEMANTIC_MIN = 0.0


async def search_kind(
    *,
    tenant_id: str,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return Brain Voyage hits. Empty when Voyage is not configured or index is not ready."""

    if not (query or "").strip() or not (tenant_id or "").strip():
        return []
    from services.brain.retrieve.orchestrate import RetrieveContext, retrieve_published

    families = {kind} if kind else None
    try:
        bundle = await retrieve_published(
            RetrieveContext(tenant_id=tenant_id, query=query, families=families)  # type: ignore[arg-type]
        )
    except Exception:
        return []
    if bundle.outcome in {
        "provider_not_configured",
        "provider_error",
        "index_not_ready",
        "unpublished",
        "product_index_stale",
    }:
        return []
    hits: list[dict[str, Any]] = []
    for item in bundle.items:
        if kind and item.source_family != kind:
            continue
        answer = item.text if item.source_family == "faq" else ""
        hits.append(
            {
                "source_id": item.source_id,
                "kind": item.source_family,
                "language": language or "",
                "text": item.text,
                "score": 1.0,
                "metadata": {
                    "answer": answer,
                    "language": language or "",
                    "title": item.title,
                    **(item.extra or {}),
                },
            }
        )
        if len(hits) >= top_k:
            break
    return [hit for hit in hits if float(hit.get("score") or 0) >= _FAQ_SEMANTIC_MIN]
