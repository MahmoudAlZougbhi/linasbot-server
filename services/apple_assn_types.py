"""Explicit ASSN V2 notification-type → action / entitlement-status mapping.

Unknown types must never fall through to ``active``. Prefer
``classify_assn_action`` over ad-hoc string checks in the processor.
"""

from __future__ import annotations

from typing import Any, Literal

from services.entitlements_service import EntitlementStatus

AssnAction = Literal[
    "apply_txn",
    "refund",
    "refund_reversed",
    "consumption",
    "metadata",
    "ignore",
    "error",
]

# Activating subscription lifecycle events → entitlement active.
_ACTIVATING: frozenset[str] = frozenset(
    {
        "SUBSCRIBED",
        "DID_RENEW",
        "OFFER_REDEEMED",
        "INITIAL_BUY",
    }
)

# Billing / grace lifecycle → entitlement grace (never active).
_GRACE: frozenset[str] = frozenset(
    {
        "GRACE_PERIOD",
        "DID_FAIL_TO_RENEW",
        "BILLING_RETRY",
        "GRACE_PERIOD_EXPIRED",
    }
)

# Metadata-only: record / renew-info side effects; NO status → active.
_METADATA_ONLY: frozenset[str] = frozenset(
    {
        "PRICE_INCREASE",
        "RENEWAL_EXTENDED",
        "DID_CHANGE_RENEWAL_PREF",
    }
)

_KNOWN: frozenset[str] = (
    _ACTIVATING
    | _GRACE
    | _METADATA_ONLY
    | frozenset(
        {
            "EXPIRED",
            "REFUND",
            "REVOKE",
            "REFUND_REVERSED",
            "DID_CHANGE_RENEWAL_STATUS",
            "ONE_TIME_CHARGE",
            "CONSUMPTION_REQUEST",
            "TEST",
            "CANCEL",
        }
    )
)


def status_for_notification_type(
    notification_type: str,
    *,
    subtype: str | None = None,
) -> EntitlementStatus | None:
    """Map ASSN type → entitlement status, or None when status must not change.

    Raises ``ValueError`` for unknown types (never defaults to active).
    """
    t = (notification_type or "").strip().upper()
    st = (subtype or "").strip().upper() or None
    if not t:
        raise ValueError("notification_type required")
    if t in _ACTIVATING:
        return "active"
    if t in _GRACE:
        return "grace"
    if t == "EXPIRED":
        return "expired"
    if t == "REFUND":
        return "refunded"
    if t == "REVOKE":
        return "revoked"
    if t in {"CANCEL"}:
        return "canceled"
    if t == "DID_CHANGE_RENEWAL_STATUS":
        # AUTO_RENEW_ENABLED must not force active; only disabled → canceled.
        if st == "AUTO_RENEW_ENABLED":
            return None
        return "canceled"
    if t in _METADATA_ONLY or t in {"ONE_TIME_CHARGE", "CONSUMPTION_REQUEST", "TEST", "REFUND_REVERSED"}:
        return None
    if t not in _KNOWN:
        raise ValueError(f"unknown ASSN notification type: {t}")
    raise ValueError(f"ASSN type has no entitlement status mapping: {t}")


def classify_assn_action(
    notification_type: str,
    subtype: str | None = None,
) -> dict[str, Any]:
    """Classify how ``process_notification_v2`` should handle an ASSN event.

    Fields:
      action: apply_txn|refund|refund_reversed|consumption|metadata|ignore|error
      status: EntitlementStatus | None (None = do not change entitlement status)
      effect_kind: optional tag (e.g. metadata_only, consumable_only)
      notification_type / subtype: normalized
    """
    t = (notification_type or "").strip().upper()
    st = (subtype or "").strip().upper() or None
    base: dict[str, Any] = {
        "notification_type": t,
        "subtype": st,
        "status": None,
        "effect_kind": None,
    }
    if not t:
        return {**base, "action": "error", "reason": "missing_notification_type"}

    if t == "TEST":
        return {**base, "action": "ignore", "effect_kind": "test"}
    if t == "CONSUMPTION_REQUEST":
        return {**base, "action": "consumption"}
    if t == "REFUND_REVERSED":
        return {**base, "action": "refund_reversed", "status": "active"}
    if t == "REFUND":
        return {**base, "action": "refund", "status": "refunded"}
    if t == "REVOKE":
        return {**base, "action": "refund", "status": "revoked"}
    if t in _METADATA_ONLY:
        return {**base, "action": "metadata", "effect_kind": "metadata_only"}
    if t == "ONE_TIME_CHARGE":
        return {**base, "action": "apply_txn", "effect_kind": "consumable_only"}
    if t == "DID_CHANGE_RENEWAL_STATUS":
        if st == "AUTO_RENEW_ENABLED":
            return {**base, "action": "metadata", "effect_kind": "renewal_status_enabled"}
        return {**base, "action": "apply_txn", "status": "canceled", "effect_kind": "renewal_status"}
    if t in _ACTIVATING:
        return {**base, "action": "apply_txn", "status": "active"}
    if t in _GRACE:
        return {**base, "action": "apply_txn", "status": "grace"}
    if t == "EXPIRED":
        return {**base, "action": "apply_txn", "status": "expired"}
    if t == "CANCEL":
        return {**base, "action": "apply_txn", "status": "canceled"}
    if t not in _KNOWN:
        return {
            **base,
            "action": "ignore",
            "effect_kind": "failed_unknown_type",
            "reason": "failed_unknown_type",
        }
    return {**base, "action": "error", "reason": f"unhandled_known_type:{t}"}
