"""Turn budgets from the implementation contract. Tunable, enforced globally."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnBudgets:
    history_visible_cap: int = 50
    lexical_candidates_per_source: int = 20
    semantic_candidates_per_source: int = 20
    rerank_cap_per_task: int = 40
    evidence_chunks_before_expand: int = 6
    extra_retrieval_rounds: int = 1
    # Kept at 1 (honest). P1 generate/reply must consume this for one grounding repair.
    repair_attempts: int = 1
    embedding_dimensions: int = 1024


DEFAULT_BUDGETS = TurnBudgets()
SCHEMA_VERSION = "customer_ai.v1"
