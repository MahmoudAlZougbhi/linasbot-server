"""Server-owned Customer AI message classification. Not token or credit math."""

from __future__ import annotations

from typing import Final, Literal

from services.membership.message_catalog import MESSAGE_POLICY_VERSION

ResponseClass = Literal[
    "generated_ai",
    "mixed_faq_ai",
    "followup_sent",
    "faq_only",
    "static",
    "resource_only",
    "no_reply",
    "owner_or_internal",
    "operational_notice",
]

ZERO_DEBIT: Final[frozenset[str]] = frozenset(
    {
        "faq_only",
        "static",
        "resource_only",
        "no_reply",
        "owner_or_internal",
        "operational_notice",
    }
)


def message_units_for(response_class: ResponseClass) -> int:
    if response_class in ZERO_DEBIT:
        return 0
    if response_class in {"generated_ai", "mixed_faq_ai", "followup_sent"}:
        return 1
    raise ValueError(f"unknown response class: {response_class}")


def classify_turn(
    *,
    generated: bool,
    faq_used: bool,
    followup_sent: bool = False,
    static: bool = False,
    resource_only: bool = False,
    no_reply: bool = False,
    owner_or_internal: bool = False,
) -> ResponseClass:
    if owner_or_internal:
        return "owner_or_internal"
    if no_reply:
        return "no_reply"
    if static:
        return "static"
    if resource_only and not generated:
        return "resource_only"
    if followup_sent:
        return "followup_sent"
    if faq_used and generated:
        return "mixed_faq_ai"
    if faq_used and not generated:
        return "faq_only"
    if generated:
        return "generated_ai"
    return "operational_notice"


def policy_meta() -> dict[str, str]:
    return {
        "message_policy_version": MESSAGE_POLICY_VERSION,
        "unit": "messages",
    }
