"""Deprecated customer-engine flag stubs. Brain uses providers.config — do not revive a retrieval LLM."""

from __future__ import annotations

from typing import Any


def customer_ai_v10_runtime_enabled() -> bool:
    return False


def customer_semantic_retrieval_enabled() -> bool:
    """Legacy flag name kept for imports; always False. Brain Voyage retrieve is separate."""
    return False


def flags_snapshot() -> dict[str, Any]:
    return {
        "customer_engine": "brain_or_removed",
        "v10": False,
        "semantic_retrieval_legacy": False,
        "note": "Customer Brain is the only reply engine when enabled; retrieval is Voyage embeddings.",
    }


def customer_answer_model_name() -> str:
    """Deprecated stub — use services.brain.providers.config.answer_model."""
    return "customer_brain_answer"


def customer_retrieval_model_name() -> str:
    """Deprecated stub — Brain uses Voyage entity spaces, not an LLM retriever."""
    return "customer_brain_voyage_entity"
