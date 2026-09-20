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
    max_retrieval_rounds: int = 3
    max_agent_steps: int = 6
    max_tool_calls: int = 8
    # Rounds after the first (= max_retrieval_rounds - 1).
    extra_retrieval_rounds: int = 2
    # Kept at 1 (honest). P1 generate/reply must consume this for one grounding repair.
    repair_attempts: int = 1
    verifier_repairs: int = 1
    embedding_dimensions: int = 1024


DEFAULT_BUDGETS = TurnBudgets()
SCHEMA_VERSION = "customer_ai.v1"


def budgets_for_tenant(tenant_id: str | None = None) -> TurnBudgets:
    """Portal Live runtime_limits merged onto code defaults."""
    tid = (tenant_id or "").strip()
    if not tid:
        return DEFAULT_BUDGETS
    from services.runtime_limits.loader import load_runtime_limits

    lim = load_runtime_limits(tid)
    extra = max(0, lim.max_retrieval_rounds - 1)
    return TurnBudgets(
        history_visible_cap=lim.customer_history_messages,
        max_retrieval_rounds=lim.max_retrieval_rounds,
        max_agent_steps=lim.max_agent_steps,
        max_tool_calls=lim.max_tool_calls,
        extra_retrieval_rounds=extra,
    )
