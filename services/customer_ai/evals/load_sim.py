"""Safe offline load simulation for Customer Brain lexical path (no production traffic)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from services.customer_ai.evals.fixtures import hospitality_corpus, knowledge_heavy_corpus
from services.customer_ai.evals.metrics import mean, percentile
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.lexical import search_cards


def run_load_simulation(
    *,
    tenants: int = 100,
    requests_per_tenant: int = 5,
    workers: int = 8,
) -> dict[str, Any]:
    sections = {**hospitality_corpus(), **knowledge_heavy_corpus()}
    cards = cards_from_sections(sections)
    queries = [
        "opening hours",
        "laser price",
        "full body",
        "product stock",
        "book appointment",
    ]
    latencies: list[float] = []
    errors = 0

    def _one(seed: int) -> float:
        query = queries[seed % len(queries)]
        started = time.perf_counter()
        search_cards(cards, f"{query} t{seed}", limit=10)
        return (time.perf_counter() - started) * 1000.0

    jobs = tenants * requests_per_tenant
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, i) for i in range(jobs)]
        for fut in as_completed(futures):
            try:
                latencies.append(float(fut.result()))
            except Exception:
                errors += 1
    elapsed = sum(latencies) / 1000.0 if latencies else 0.0
    return {
        "environment": "offline_local_lexical_only",
        "live_spend": False,
        "production_traffic": False,
        "tenants_simulated": tenants,
        "requests": jobs,
        "workers": workers,
        "error_rate": (errors / jobs) if jobs else 0.0,
        "throughput_rps_approx": (jobs / elapsed) if elapsed > 0 else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "mean": mean(latencies),
        },
        "note": "Does not exercise Voyage/OpenAI/DB pools. Do not extrapolate production capacity.",
    }
