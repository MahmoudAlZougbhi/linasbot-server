"""Code defaults + range clamps for portal runtime limits."""

from __future__ import annotations

from dataclasses import dataclass

HISTORY_MIN, HISTORY_MAX = 1, 500
CAP_MIN, CAP_MAX = 1, 200
ROUNDS_MIN, ROUNDS_MAX = 1, 10
STEPS_MIN, STEPS_MAX = 1, 20
OWNER_CHARS_MAX = 100000
CUSTOMER_CHARS_MAX = 10000


@dataclass(frozen=True)
class RuntimeLimits:
    owner_history_messages: int = 100
    owner_message_max_chars: int = 0
    customer_history_messages: int = 50
    customer_message_max_chars: int = 600
    product_search_cap: int = 24
    catalog_evidence_cap: int = 18
    max_retrieval_rounds: int = 3
    max_agent_steps: int = 6
    max_tool_calls: int = 8


DEFAULT_LIMITS = RuntimeLimits()


def _int(raw: object, default: int, lo: int, hi: int) -> int:
    if isinstance(raw, bool) or raw is None:
        return default
    try:
        if isinstance(raw, int):
            value = raw
        elif isinstance(raw, float):
            value = int(raw)
        elif isinstance(raw, str) and raw.strip():
            value = int(raw.strip())
        else:
            return default
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def clamp_payload(raw: dict[str, object] | None) -> RuntimeLimits:
    src = raw if isinstance(raw, dict) else {}
    owner_chars = src.get("owner_message_max_chars")
    if owner_chars is None or owner_chars == "":
        owner_max = 0
    else:
        owner_max = _int(owner_chars, 0, 0, OWNER_CHARS_MAX)
    customer_chars = src.get("customer_message_max_chars")
    if customer_chars is None or customer_chars == "":
        customer_max = DEFAULT_LIMITS.customer_message_max_chars
    else:
        customer_max = _int(customer_chars, DEFAULT_LIMITS.customer_message_max_chars, 0, CUSTOMER_CHARS_MAX)
    return RuntimeLimits(
        owner_history_messages=_int(
            src.get("owner_history_messages"), DEFAULT_LIMITS.owner_history_messages, HISTORY_MIN, HISTORY_MAX
        ),
        owner_message_max_chars=owner_max,
        customer_history_messages=_int(
            src.get("customer_history_messages"),
            DEFAULT_LIMITS.customer_history_messages,
            HISTORY_MIN,
            HISTORY_MAX,
        ),
        customer_message_max_chars=customer_max,
        product_search_cap=_int(src.get("product_search_cap"), DEFAULT_LIMITS.product_search_cap, CAP_MIN, CAP_MAX),
        catalog_evidence_cap=_int(
            src.get("catalog_evidence_cap"), DEFAULT_LIMITS.catalog_evidence_cap, CAP_MIN, CAP_MAX
        ),
        max_retrieval_rounds=_int(
            src.get("max_retrieval_rounds"), DEFAULT_LIMITS.max_retrieval_rounds, ROUNDS_MIN, ROUNDS_MAX
        ),
        max_agent_steps=_int(src.get("max_agent_steps"), DEFAULT_LIMITS.max_agent_steps, STEPS_MIN, STEPS_MAX),
        max_tool_calls=_int(src.get("max_tool_calls"), DEFAULT_LIMITS.max_tool_calls, STEPS_MIN, STEPS_MAX),
    )
