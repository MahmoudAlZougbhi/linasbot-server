"""Customer Reply AI V2 feature flags and kill switches.

Defaults keep production on the existing published CM pipeline until Mahmoud
explicitly enables V2 live send. No silent model downgrades.
"""

from __future__ import annotations

import os

DEFAULT_CUSTOMER_MODEL = "gpt-5.6-terra"
MAX_CUSTOMER_RETRIEVAL_ROUNDS = 2
DM_CONTEXT_WINDOW_HOURS = 3


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def customer_reply_ai_v2_enabled() -> bool:
    """Master switch. When false, existing published CM runtime remains authoritative."""
    return _truthy("CUSTOMER_REPLY_AI_V2", "false")


def customer_reply_ai_v2_live_send() -> bool:
    """When false (shadow), V2 plans/runs but callers keep the pre-V2 customer-visible reply."""
    return _truthy("CUSTOMER_REPLY_AI_V2_LIVE", "false")


def customer_semantic_retrieval_enabled() -> bool:
    """Hierarchical Retrieval for customer social. Defaults on when V2 is on."""
    if not customer_reply_ai_v2_enabled():
        return False
    raw = os.getenv("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED")
    if raw is None or not str(raw).strip():
        return True
    return _truthy("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED", "true")


def customer_media_context_enabled() -> bool:
    """Comment image/carousel/video cached context. Default off until soak."""
    return _truthy("CUSTOMER_MEDIA_CONTEXT_ENABLED", "false")


def customer_model_name() -> str:
    """Canonical customer social model from policy (gpt-5.6-terra). No silent fallback."""
    from services.model_policy import assert_customer_social_model, customer_social_model_id

    return assert_customer_social_model(customer_social_model_id())


def max_retrieval_rounds() -> int:
    raw = (os.getenv("MAX_CUSTOMER_RETRIEVAL_ROUNDS") or str(MAX_CUSTOMER_RETRIEVAL_ROUNDS)).strip()
    try:
        return max(1, min(2, int(raw)))
    except ValueError:
        return MAX_CUSTOMER_RETRIEVAL_ROUNDS


def dm_context_window_hours() -> float:
    raw = (os.getenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS") or str(DM_CONTEXT_WINDOW_HOURS)).strip()
    try:
        return max(0.25, min(24.0, float(raw)))
    except ValueError:
        return float(DM_CONTEXT_WINDOW_HOURS)


def customer_context_token_budget() -> int:
    raw = (os.getenv("LINAS_CUSTOMER_CONTEXT_BUDGET") or "8000").strip()
    try:
        return max(1500, min(32000, int(raw)))
    except ValueError:
        return 8000


def flags_snapshot() -> dict[str, object]:
    return {
        "CUSTOMER_REPLY_AI_V2": customer_reply_ai_v2_enabled(),
        "CUSTOMER_REPLY_AI_V2_LIVE": customer_reply_ai_v2_live_send(),
        "CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED": customer_semantic_retrieval_enabled(),
        "CUSTOMER_MEDIA_CONTEXT_ENABLED": customer_media_context_enabled(),
        "LINAS_CUSTOMER_MODEL": customer_model_name(),
        "MAX_CUSTOMER_RETRIEVAL_ROUNDS": max_retrieval_rounds(),
        "CUSTOMER_DM_CONTEXT_WINDOW_HOURS": dm_context_window_hours(),
        "shadow_mode": customer_reply_ai_v2_enabled() and not customer_reply_ai_v2_live_send(),
    }
