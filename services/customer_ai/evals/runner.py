"""Offline fixture checks. No live provider spend."""

from __future__ import annotations

import time
from typing import Any

from services.customer_ai.evals.contract_cases import run_contract_cases
from services.customer_ai.evals.fixtures import (
    hospitality_corpus,
    knowledge_heavy_corpus,
    product_retailer_corpus,
    service_appointment_corpus,
)
from services.customer_ai.evals.golden_pack_linas import run_golden_pack_linas
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_ranked
from services.customer_ai.retrieve.lexical import LexicalHit, search_cards


def all_corpora() -> dict[str, dict[str, Any]]:
    return {
        "hospitality": hospitality_corpus(),
        "knowledge_heavy": knowledge_heavy_corpus(),
        "product_retailer": product_retailer_corpus(),
        "service_appointment": service_appointment_corpus(),
    }


def _queries(sections: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    for payload in sections.values():
        if not isinstance(payload, dict):
            continue
        rows = payload.get("items") or payload.get("catalog") or []
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
            title = str(item.get("title") or labels.get("en") or item.get("id") or "").strip()
            if title:
                queries.append(title)
    return queries


def _metric_hooks(*, latency_ms: float, case_count: int) -> dict[str, Any]:
    """Latency/cost metric hooks (stubs OK until live metering lands)."""
    return {
        "latency_ms": round(latency_ms, 3),
        "cost_usd_stub": 0.0,
        "live_spend": False,
        "cases_per_second": round(case_count / (latency_ms / 1000.0), 3) if latency_ms > 0 else None,
    }


def run_fixture_corpus() -> dict[str, Any]:
    started = time.perf_counter()
    cases: list[dict[str, Any]] = []
    for name, sections in all_corpora().items():
        cards = cards_from_sections(sections)
        for query in _queries(sections):
            plan = plan_message(query)
            hits = search_cards(cards, query, limit=3)
            bundle = expand_ranked(hits or [LexicalHit(card=card, score=1.0) for card in cards[:1]], sections)
            cases.append(
                {
                    "corpus": name,
                    "query": query,
                    "task_types": [task.type for task in plan.tasks],
                    "read_only": plan.read_only,
                    "retrieve_outcome": bundle.outcome,
                    "evidence": len(bundle.items),
                }
            )
    contract = run_contract_cases()
    golden = run_golden_pack_linas()
    from services.customer_ai.evals.latency_bench import run_latency_benchmark
    from services.customer_ai.evals.suite_runner import run_offline_suite

    offline = run_offline_suite(write_artifact=True)
    latency = run_latency_benchmark(repeats=20)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    total_cases = int(offline.get("summary", {}).get("case_count") or 0) + int(
        contract.get("case_count") or 0
    ) + int(golden.get("case_count") or 0)
    return {
        "ok": bool(contract.get("ok")) and bool(golden.get("ok")) and bool(offline.get("gates", {}).get("case_count_ge_800")),
        "live_spend": False,
        "case_count": total_cases,
        "cases": cases,
        "contract_cases": contract.get("cases") or [],
        "golden_pack_linas": golden,
        "offline_suite": {
            "ok": offline.get("ok"),
            "gates": offline.get("gates"),
            "summary": offline.get("summary"),
            "artifact": offline.get("artifact"),
        },
        "latency_bench": latency,
        "metrics": _metric_hooks(latency_ms=elapsed_ms, case_count=total_cases),
    }
