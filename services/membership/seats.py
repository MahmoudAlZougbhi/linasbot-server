"""Seat limit enforcement: owner excluded; active members + pending invites count."""

from __future__ import annotations

from typing import Any

from services.membership.feature_entitlements import additional_seats_for_plan
from services.membership.plan_catalog import require_plan


class SeatLimitExceeded(PermissionError):
    code = "SEAT_LIMIT_EXCEEDED"


def seat_usage(*, active_non_owner_members: int, pending_invitations: int) -> int:
    return max(0, int(active_non_owner_members)) + max(0, int(pending_invitations))


def assert_can_add_seat(
    plan_id: str,
    *,
    active_non_owner_members: int,
    pending_invitations: int,
) -> dict[str, Any]:
    known, limit = additional_seats_for_plan(plan_id)
    if not known:
        limit = require_plan(plan_id).additional_seats
    used = seat_usage(
        active_non_owner_members=active_non_owner_members,
        pending_invitations=pending_invitations,
    )
    if limit is None:
        return {
            "plan_id": plan_id,
            "used": used,
            "limit": None,
            "unlimited": True,
            "remaining": None,
        }
    if used >= limit:
        raise SeatLimitExceeded(f"Additional seat limit reached for plan={plan_id}: {used}/{limit}")
    return {
        "plan_id": plan_id,
        "used": used,
        "limit": limit,
        "unlimited": False,
        "remaining": max(0, limit - used),
    }
