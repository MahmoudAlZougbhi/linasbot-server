"""Owner System Copilot V2 feature flags and kill switches.

No silent model downgrades. Rollbacks are explicit env flags only.
"""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def owner_copilot_v2_enabled() -> bool:
    """Sol brain is the only Owner Copilot path. V1 is deleted."""
    return True


def owner_copilot_writes_enabled() -> bool:
    """Always-on propose→Approve→Live. Env OWNER_COPILOT_WRITES is ignored."""
    return True


def owner_copilot_meta_actions_enabled() -> bool:
    """External Meta mutations (disconnect/reconnect/token/webhook). Default off — V2 diagnosis is read-only."""
    return _truthy("OWNER_COPILOT_META_ACTIONS", "false")


def owner_copilot_shadow_planning() -> bool:
    """Explicit opt-in read-only planning. Not the default; does not follow WRITES env."""
    return _truthy("OWNER_COPILOT_SHADOW_PLANNING", "false")


def owner_model_name() -> str:
    """Single canonical owner brain from model policy (gpt-5.6-sol). No mini fallback."""
    from services.brain.model_policy import owner_model_id

    return owner_model_id()


def guest_model_name_v2() -> str:
    return (os.getenv("LINAS_GUEST_MODEL") or "gpt-5.6-sol").strip() or "gpt-5.6-sol"


def owner_max_output_tokens(*, reasoning_effort: str | None = None) -> int:
    """Owner reply completion budget.

    Env ``LINAS_OWNER_MAX_OUTPUT_TOKENS`` overrides when set. Otherwise scale by
    reasoning effort: High burns invisible reasoning tokens inside
    ``max_completion_tokens``, so a flat 1200 budget truncates long Work/High
    replies mid-sentence (seen as CM review stopping at section 12).
    """
    raw = (os.getenv("LINAS_OWNER_MAX_OUTPUT_TOKENS") or "").strip()
    if raw:
        try:
            return max(256, min(8192, int(raw)))
        except ValueError:
            pass
    effort = (reasoning_effort or "").strip().lower()
    if effort == "high":
        return 4096
    if effort == "low":
        return 2048
    return 3072


def owner_context_token_budget() -> int:
    """Overall owner turn context budget (system + tools + history overhead)."""
    raw = (os.getenv("LINAS_OWNER_CONTEXT_BUDGET") or "6000").strip()
    try:
        return max(1500, min(32000, int(raw)))
    except ValueError:
        return 6000


def owner_recent_history_tokens() -> int:
    """Optional last-resort token ceiling for Owner Copilot history.

    Sol packs the last N portal messages (default 100) at full length.
    This env is only used when a caller passes token_budget explicitly.
    """
    raw = (os.getenv("LINAS_OWNER_RECENT_HISTORY_TOKENS") or "4000").strip()
    try:
        return max(500, min(32000, int(raw)))
    except ValueError:
        return 4000


def flags_snapshot() -> dict[str, object]:
    return {
        "OWNER_COPILOT_V2": owner_copilot_v2_enabled(),
        "OWNER_COPILOT_WRITES": owner_copilot_writes_enabled(),
        "OWNER_COPILOT_META_ACTIONS": owner_copilot_meta_actions_enabled(),
        "OWNER_COPILOT_SHADOW_PLANNING": owner_copilot_shadow_planning(),
        "LINAS_OWNER_MODEL": owner_model_name(),
        "LINAS_GUEST_MODEL": guest_model_name_v2(),
        "LINAS_OWNER_MAX_OUTPUT_TOKENS": owner_max_output_tokens(),
        "LINAS_OWNER_CONTEXT_BUDGET": owner_context_token_budget(),
        "LINAS_OWNER_RECENT_HISTORY_TOKENS": owner_recent_history_tokens(),
    }
