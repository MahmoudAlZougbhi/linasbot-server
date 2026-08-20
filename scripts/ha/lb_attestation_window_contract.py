#!/usr/bin/env python3
"""LB attestation freshness vs the authorized HA drain wait.

The operator observation must be <= 300 seconds old when a mutation starts.
Recover then sleeps the durable drain (30-300 seconds) before admission.
Re-applying the 300-second dispatch window after that authorized wait is a
deadlock: drain_seconds of 180+ always expires the same attestation.

Post-drain checks keep the same installed observation (digest + observed_at)
and allow age up to OPERATOR_FRESHNESS_SECONDS + drain_seconds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

OPERATOR_FRESHNESS_SECONDS = 300
MIN_DRAIN_SECONDS = 30
MAX_DRAIN_SECONDS = 300
CLOCK_SKEW_SECONDS = 30

ALREADY_DRAINED_RECOVERY_PHASES = frozenset(
    {
        "automatic-rollback-both-nodes-drained",
        "recovery-both-nodes-drained",
        "rollback-restoring",
        "distinct-rollback-drained",
        "rollback-peer-admit",
        "rollback-node01-admit",
        "commit-recovery-parity",
        "commit-peer-admit",
        "commit-node01-admit",
    }
)


def validate_drain_seconds(drain_seconds: int) -> int:
    if type(drain_seconds) is not int or isinstance(drain_seconds, bool):
        raise SystemExit("HA load-balancer drain interval must be between 30 and 300 seconds")
    if not MIN_DRAIN_SECONDS <= drain_seconds <= MAX_DRAIN_SECONDS:
        raise SystemExit("HA load-balancer drain interval must be between 30 and 300 seconds")
    return drain_seconds


def mutation_window_seconds(drain_seconds: int) -> int:
    drain = validate_drain_seconds(drain_seconds)
    return OPERATOR_FRESHNESS_SECONDS + drain


def skip_extra_drain_wait(phase: str) -> bool:
    return phase in ALREADY_DRAINED_RECOVERY_PHASES


def attestation_within_window(
    *,
    observed_at: datetime,
    now: datetime,
    max_age_seconds: int,
) -> bool:
    if type(max_age_seconds) is not int or isinstance(max_age_seconds, bool):
        raise SystemExit("LB attestation mutation window is invalid")
    if not OPERATOR_FRESHNESS_SECONDS <= max_age_seconds <= (OPERATOR_FRESHNESS_SECONDS + MAX_DRAIN_SECONDS):
        raise SystemExit("LB attestation mutation window is invalid")
    if observed_at.tzinfo is None or now.tzinfo is None:
        raise SystemExit("LB attestation observation time is invalid")
    if observed_at > now + timedelta(seconds=CLOCK_SKEW_SECONDS):
        return False
    return now - observed_at <= timedelta(seconds=max_age_seconds)


def parse_observed_at(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise SystemExit("LB attestation observation time is invalid")
    return datetime.fromisoformat(raw[:-1] + "+00:00").astimezone(UTC)
