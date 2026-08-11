"""Seat limit enforcement: owner excluded; active members + pending invites count."""

from __future__ import annotations

from typing import Any

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
    plan = require_plan(plan_id)
    used = seat_usage(
        active_non_owner_members=active_non_owner_members,
        pending_invitations=pending_invitations,
    )
    limit = plan.additional_seats
    unlimited = limit is None
    if not unlimited and used >= int(limit):
        raise SeatLimitExceeded(f"Additional seat limit reached for plan={plan_id}: {used}/{limit}")
    return {
        "plan_id": plan_id,
        "used": used,
        "limit": limit,
        "unlimited": unlimited,
        "remaining": None if unlimited else max(0, int(limit) - used),
    }
