"""Recheck follow-up immediately before delivery. Empty generation may be no_reply."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FollowupRecheck:
    allow: bool
    reason: str


def revalidate_followup_send(
    *,
    customer_replied: bool = False,
    takeover: bool = False,
    opt_out: bool = False,
    goal_completed: bool = False,
    window_valid: bool = True,
    rule_permits: bool = True,
) -> FollowupRecheck:
    if customer_replied:
        return FollowupRecheck(False, "customer_replied")
    if takeover:
        return FollowupRecheck(False, "human_control")
    if opt_out:
        return FollowupRecheck(False, "opt_out")
    if goal_completed:
        return FollowupRecheck(False, "goal_completed")
    if not window_valid:
        return FollowupRecheck(False, "channel_window_closed")
    if not rule_permits:
        return FollowupRecheck(False, "rule_changed")
    return FollowupRecheck(True, "ok")
