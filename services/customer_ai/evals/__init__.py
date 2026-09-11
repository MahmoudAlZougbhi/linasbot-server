"""Eval fixtures."""

from __future__ import annotations

from services.customer_ai.evals.case_bank import case_bank_snapshot
from services.customer_ai.evals.fixtures import (
    hospitality_corpus,
    knowledge_heavy_corpus,
    product_retailer_corpus,
    service_appointment_corpus,
)
from services.customer_ai.evals.golden_pack_linas import run_golden_pack_linas
from services.customer_ai.evals.latency_bench import run_latency_benchmark
from services.customer_ai.evals.runner import run_fixture_corpus
from services.customer_ai.evals.suite_runner import run_offline_suite

__all__ = [
    "hospitality_corpus",
    "knowledge_heavy_corpus",
    "product_retailer_corpus",
    "service_appointment_corpus",
    "run_fixture_corpus",
    "run_golden_pack_linas",
    "run_offline_suite",
    "case_bank_snapshot",
    "run_latency_benchmark",
]
