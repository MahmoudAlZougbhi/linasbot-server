"""Customer-engine flags. Luna/Terra runtime is removed; Sol owner path is unchanged."""

from __future__ import annotations

from typing import Any


def customer_ai_v10_runtime_enabled() -> bool:
    return False


def customer_semantic_retrieval_enabled() -> bool:
    return False


def flags_snapshot() -> dict[str, Any]:
    return {"customer_engine": "removed", "v10": False}


def customer_answer_model_name() -> str:
    return "gpt-5.6-terra"


def customer_retrieval_model_name() -> str:
    return "gpt-5.6-luna"
