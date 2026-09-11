"""Retrieval cases derived from a tenant's published cards (no lab-only corpus)."""

from __future__ import annotations

import time
from typing import Any

from services.customer_ai.evals.metrics import mean, percentile, retrieval_row
from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.voyage_client import VoyageContractError
from services.customer_ai.retrieve.cards import TitleCard, load_published_cards
from services.customer_ai.retrieve.hybrid import search_hybrid

_MAX_CASES = 16


def cases_from_cards(cards: list[TitleCard]) -> list[dict[str, Any]]:
    per_family: dict[str, int] = {}
    cases: list[dict[str, Any]] = []
    for card in cards:
        family = str(card.source_family or "")
        taken = per_family.get(family, 0)
        if taken >= 2:
            continue
        source_id = card.item_id.split(":", 1)[-1]
        if not card.title or not source_id:
            continue
        queries = [card.title]
        for alias in card.aliases[:1]:
            if alias and alias not in queries:
                queries.append(alias)
        for index, query in enumerate(queries[:2]):
            cases.append(
                {
                    "id": f"{family}:{source_id}:{index}",
                    "q": query,
                    "families": {family} if family else None,
                    "relevant": {source_id},
                }
            )
        per_family[family] = taken + 1
        if len(cases) >= _MAX_CASES:
            break
    return cases


async def retrieval_eval_for_tenant(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not voyage_configured():
        return {"status": "BLOCKED", "detail": "VOYAGE_API_KEY", "tenant_id": tid}
    cards = load_published_cards(tid)
    if not cards:
        return {"status": "FAIL", "detail": "no_published_cards", "tenant_id": tid}
    cases = cases_from_cards(cards)
    if not cases:
        return {"status": "FAIL", "detail": "no_retrieval_cases", "tenant_id": tid}
    rows: list[dict[str, float]] = []
    failures: list[str] = []
    latencies: list[float] = []
    for case in cases:
        t0 = time.perf_counter()
        try:
            families = case.get("families")
            hits = await search_hybrid(
                cards,
                str(case["q"]),
                families=set(families) if families else None,
                limit=10,
                tenant_id=tid,
            )
        except VoyageContractError as exc:
            if "429" in str(exc):
                return {"status": "BLOCKED", "detail": "voyage_rate_limited", "tenant_id": tid}
            return {"status": "FAIL", "detail": f"voyage_error:{type(exc).__name__}", "tenant_id": tid}
        latencies.append(time.perf_counter() - t0)
        ranked = [h.card.item_id.split(":", 1)[-1] for h in hits]
        metrics = retrieval_row(set(case["relevant"]), ranked)
        rows.append(metrics)
        if metrics["recall@10"] < 1.0:
            failures.append(f"{case['id']}: ranked={ranked[:5]}")
    agg = {k: mean(r[k] for r in rows) for k in rows[0]} if rows else {}
    gate_ok = bool(agg) and agg.get("recall@10", 0.0) >= 0.98
    return {
        "status": "PASS" if gate_ok else "FAIL",
        "detail": "recall@10>=0.98" if gate_ok else "recall@10_below_gate",
        "tenant_id": tid,
        "metrics": agg,
        "failures": failures,
        "latency_p50": percentile(latencies, 0.50),
        "latency_p95": percentile(latencies, 0.95),
        "n": len(rows),
        "families": sorted({str(card.source_family) for card in cards}),
    }
