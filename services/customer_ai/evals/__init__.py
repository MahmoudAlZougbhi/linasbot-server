"""Eval fixtures."""

from __future__ import annotations

from services.customer_ai.evals.runner import run_fixture_corpus
from services.customer_ai.evals.fixtures import (
    hospitality_corpus,
    knowledge_heavy_corpus,
    product_retailer_corpus,
    service_appointment_corpus,
)

__all__ = [
    "hospitality_corpus",
    "knowledge_heavy_corpus",
    "product_retailer_corpus",
    "service_appointment_corpus",
    "run_fixture_corpus",
]
