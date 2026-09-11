"""Offline fixture checks. No live provider spend."""

from __future__ import annotations

from typing import Any

from services.customer_ai.evals.contract_cases import run_contract_cases
from services.customer_ai.evals.fixtures import (
    hospitality_corpus,
    knowledge_heavy_corpus,
    product_retailer_corpus,
    service_appointment_corpus,
)
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.retrieve.expand import expand_ranked
from services.customer_ai.retrieve.cards import cards_from_sections
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


def run_fixture_corpus() -> dict[str, Any]:
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
    return {
        "ok": bool(contract.get("ok")),
        "live_spend": False,
        "case_count": len(cases) + int(contract.get("case_count") or 0),
        "cases": cases,
        "contract_cases": contract.get("cases") or [],
    }
