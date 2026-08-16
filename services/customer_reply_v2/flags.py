"""Customer Reply AI V2 production constants (no shadow / Classic switch).

V2 is the sole generative engine for customer IG/FB DMs and comments after
existing gates (binding, App A, plan, published CM, restricted/handoff).
There is no runtime switch back to Classic answer_generation.
"""

from __future__ import annotations

import os

MAX_CUSTOMER_RETRIEVAL_ROUNDS = 2
DM_CONTEXT_WINDOW_HOURS = 1.5  # 90 minutes
LEGACY_DM_CONTEXT_WINDOW_HOURS = 3.0


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def customer_ai_v10_runtime_enabled() -> bool:
    """Customer AI V10 runtime (safety, 90m history, metering, FAQ, Luna low, Tera low/medium).

    Rollback: CUSTOMER_AI_V10_RUNTIME=false restores the pre-v10 window, legacy FAQ
    localize path, Luna effort none, and chat.completions Tera+tools clamp.
    Default on.
    """
    raw = os.getenv("CUSTOMER_AI_V10_RUNTIME")
    if raw is None or not str(raw).strip():
        return True
    return _truthy("CUSTOMER_AI_V10_RUNTIME", "true")


def customer_semantic_retrieval_enabled() -> bool:
    """Hierarchical Retrieval Luna for customer social. Default on."""
    raw = os.getenv("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED")
    if raw is None or not str(raw).strip():
        return True
    return _truthy("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED", "true")


def customer_media_context_enabled() -> bool:
    """Comment visual context (images/carousel/thumbnails). Default on in production."""
    raw = os.getenv("CUSTOMER_MEDIA_CONTEXT_ENABLED")
    if raw is None or not str(raw).strip():
        return True
    return _truthy("CUSTOMER_MEDIA_CONTEXT_ENABLED", "true")


def customer_retrieval_model_name() -> str:
    """Retrieval-only model: GPT-5.6 Luna. Never used for final customer replies."""
    from services.model_policy import assert_customer_retrieval_model, customer_retrieval_model_id

    return assert_customer_retrieval_model(customer_retrieval_model_id())


def customer_answer_model_name() -> str:
    """Final answer + repair model: GPT-5.6 Tera + medium. Never Luna."""
    from services.model_policy import assert_customer_social_model, customer_social_model_id

    return assert_customer_social_model(customer_social_model_id())


def customer_model_name() -> str:
    """Backward-compatible alias for the answer/final model (Tera)."""
    return customer_answer_model_name()


def max_retrieval_rounds() -> int:
    raw = (os.getenv("MAX_CUSTOMER_RETRIEVAL_ROUNDS") or str(MAX_CUSTOMER_RETRIEVAL_ROUNDS)).strip()
    try:
        return max(1, min(2, int(raw)))
    except ValueError:
        return MAX_CUSTOMER_RETRIEVAL_ROUNDS


def dm_context_window_hours() -> float:
    if not customer_ai_v10_runtime_enabled():
        raw_legacy = (os.getenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS") or str(LEGACY_DM_CONTEXT_WINDOW_HOURS)).strip()
        try:
            return max(0.25, min(24.0, float(raw_legacy)))
        except ValueError:
            return float(LEGACY_DM_CONTEXT_WINDOW_HOURS)
    raw = (os.getenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS") or str(DM_CONTEXT_WINDOW_HOURS)).strip()
    try:
        return max(0.25, min(24.0, float(raw)))
    except ValueError:
        return float(DM_CONTEXT_WINDOW_HOURS)


def dm_context_window_minutes() -> float:
    return dm_context_window_hours() * 60.0


def customer_context_token_budget() -> int:
    raw = (os.getenv("LINAS_CUSTOMER_CONTEXT_BUDGET") or "8000").strip()
    try:
        return max(1500, min(32000, int(raw)))
    except ValueError:
        return 8000


def flags_snapshot() -> dict[str, object]:
    return {
        "engine": "customer_reply_v2",
        "classic_generative_fallback": False,
        "CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED": customer_semantic_retrieval_enabled(),
        "CUSTOMER_MEDIA_CONTEXT_ENABLED": customer_media_context_enabled(),
        "LINAS_CUSTOMER_RETRIEVAL_MODEL": customer_retrieval_model_name(),
        "LINAS_CUSTOMER_ANSWER_MODEL": customer_answer_model_name(),
        "MAX_CUSTOMER_RETRIEVAL_ROUNDS": max_retrieval_rounds(),
        "CUSTOMER_DM_CONTEXT_WINDOW_HOURS": dm_context_window_hours(),
        "CUSTOMER_AI_V10_RUNTIME": customer_ai_v10_runtime_enabled(),
        "history_window_minutes": dm_context_window_minutes(),
    }
