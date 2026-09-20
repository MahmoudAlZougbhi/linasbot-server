"""Portal-tunable Brain / Sol limits. Runtime reads Live published CM."""

from services.runtime_limits.defaults import DEFAULT_LIMITS, RuntimeLimits
from services.runtime_limits.loader import load_runtime_limits
from services.runtime_limits.schema import RuntimeLimitsSection
from services.runtime_limits.window import window_owner_messages_for_tenant

__all__ = [
    "DEFAULT_LIMITS",
    "RuntimeLimits",
    "RuntimeLimitsSection",
    "load_runtime_limits",
    "window_owner_messages_for_tenant",
]
