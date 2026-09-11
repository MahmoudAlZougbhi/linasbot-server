"""Offline latency micro-benchmark for Brain retrieval stages (no provider spend)."""

from __future__ import annotations

import time
from typing import Any

from services.customer_ai.evals.fixtures import hospitality_corpus, service_appointment_corpus
from services.customer_ai.evals.metrics import mean, percentile
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.lexical import search_cards


def run_latency_benchmark(*, repeats: int = 50) -> dict[str, Any]:
    sections = {**hospitality_corpus(), **service_appointment_corpus()}
    cards = cards_from_sections(sections)
    queries = [
        "opening hours",
        "laser hair removal price",
        "full body",
        "شو أوقات الدوام",
        "book appointment",
    ]
    planner_ms: list[float] = []
    bm25_ms: list[float] = []
    total_ms: list[float] = []
    for _ in range(max(1, repeats)):
        for query in queries:
            t0 = time.perf_counter()
            plan_message(query)
            t1 = time.perf_counter()
            search_cards(cards, query, limit=10)
            t2 = time.perf_counter()
            planner_ms.append((t1 - t0) * 1000.0)
            bm25_ms.append((t2 - t1) * 1000.0)
            total_ms.append((t2 - t0) * 1000.0)

    def pack(values: list[float]) -> dict[str, float]:
        return {
            "p50": percentile(values, 0.50),
            "p90": percentile(values, 0.90),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
            "mean": mean(values),
        }

    return {
        "live_spend": False,
        "repeats": repeats,
        "queries": queries,
        "stages": {
            "planner_heuristic_ms": pack(planner_ms),
            "bm25_ms": pack(bm25_ms),
            "planner_plus_bm25_ms": pack(total_ms),
        },
        "note": "Embedding/rerank/generation require providers — not included in this offline bench.",
    }
