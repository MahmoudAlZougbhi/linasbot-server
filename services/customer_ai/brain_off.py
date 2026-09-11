"""What a customer turn returns while Customer Brain is OFF.

Never restores Luna/Terra. Emergency flag stays fail-closed — only the rollback
tag restores a real answering engine.
"""

from __future__ import annotations

from services.customer_ai.flags import emergency_legacy_reply_enabled
from services.customer_reply_v2.models import ENGINE_REMOVED, CustomerReplyOutcome


def engine_removed_outcome() -> CustomerReplyOutcome:
    return CustomerReplyOutcome(
        stop=True,
        reply=None,
        reason=ENGINE_REMOVED,
        evidence_status="policy_stop",
        metadata={"ai_called": False, "cost_status": "none", "customer_engine": "removed"},
    )


def emergency_legacy_unavailable_outcome() -> CustomerReplyOutcome:
    return CustomerReplyOutcome(
        stop=True,
        reply=None,
        reason="emergency_legacy_unavailable",
        evidence_status="policy_stop",
        metadata={
            "ai_called": False,
            "cost_status": "none",
            "customer_engine": "removed",
            "rollback_required": True,
            "rollback_tag": "rollback/pre-brain-2026-09-11",
            "rollback_sha": "0f23bcf1d35886acec5dbf53eb1af2faf2734757",
        },
    )


def brain_off_outcome() -> CustomerReplyOutcome:
    if emergency_legacy_reply_enabled():
        return emergency_legacy_unavailable_outcome()
    return engine_removed_outcome()
