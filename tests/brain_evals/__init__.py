"""Eval fixtures."""

from __future__ import annotations

from tests.brain_evals.case_bank import case_bank_snapshot
from tests.brain_evals.fixtures import (
    hospitality_corpus,
    knowledge_heavy_corpus,
    product_retailer_corpus,
    service_appointment_corpus,
)
from tests.brain_evals.golden_pack import run_golden_pack
from tests.brain_evals.latency_bench import run_latency_benchmark
from tests.brain_evals.runner import run_fixture_corpus
from tests.brain_evals.suite_runner import run_offline_suite

__all__ = [
    "hospitality_corpus",
    "knowledge_heavy_corpus",
    "product_retailer_corpus",
    "service_appointment_corpus",
    "run_fixture_corpus",
    "run_golden_pack",
    "run_offline_suite",
    "case_bank_snapshot",
    "run_latency_benchmark",
]
