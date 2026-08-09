"""Owner System Copilot V2 feature flags and kill switches.

No silent model downgrades. Rollbacks are explicit env flags only.
"""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def owner_copilot_v2_enabled() -> bool:
    """Master switch for Sol brain + streaming/cards/choices protocol."""
    return _truthy("OWNER_COPILOT_V2", "true")


def owner_copilot_writes_enabled() -> bool:
    """When false (shadow mode), write tools only propose / require confirmation and never mutate."""
    return _truthy("OWNER_COPILOT_WRITES", "false")


def owner_copilot_meta_actions_enabled() -> bool:
    """External Meta mutations (disconnect/reconnect/token/webhook). Default off — V2 diagnosis is read-only."""
    return _truthy("OWNER_COPILOT_META_ACTIONS", "false")


def owner_copilot_shadow_planning() -> bool:
    """Plans and diagnoses execute read-only; no tenant writes."""
    if not owner_copilot_writes_enabled():
        return True
    return _truthy("OWNER_COPILOT_SHADOW_PLANNING", "false")


def owner_model_name() -> str:
    """Single canonical owner brain. No mini fallback."""
    return (os.getenv("LINAS_OWNER_MODEL") or "gpt-5.6-sol").strip() or "gpt-5.6-sol"


def guest_model_name_v2() -> str:
    return (os.getenv("LINAS_GUEST_MODEL") or "gpt-5.6-luna").strip() or "gpt-5.6-luna"


def owner_max_output_tokens() -> int:
    """Adaptive response budget (replaces universal 360 cap)."""
    raw = (os.getenv("LINAS_OWNER_MAX_OUTPUT_TOKENS") or "1200").strip()
    try:
        return max(256, min(8192, int(raw)))
    except ValueError:
        return 1200


def owner_context_token_budget() -> int:
    """Overall owner turn context budget (system + tools + history overhead)."""
    raw = (os.getenv("LINAS_OWNER_CONTEXT_BUDGET") or "6000").strip()
    try:
        return max(1500, min(32000, int(raw)))
    except ValueError:
        return 6000


def owner_recent_history_tokens() -> int:
    """Logged-in Owner Copilot recent chat-history read window (what the model reads).

    Explicit env — not an opaque fraction of LINAS_OWNER_CONTEXT_BUDGET.
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
