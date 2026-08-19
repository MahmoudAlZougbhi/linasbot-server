"""Fail-closed public /api/ready wait bound to the DigitalOcean LB health window.

This module is the testable contract. The dispatch helper embeds the same
probe/wait rules because recover_exact runs against an older live checkout
that does not yet contain this file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

PUBLIC_READY_URL = "https://linasaibot.com/api/ready"
PUBLIC_READY_USER_AGENT = "linasbot-ha-deploy-readiness-proof/1"
PUBLIC_READY_HEALTH_SLACK_SECONDS = 10

PRE_MUTATION_LATER_HELPER_PHASES = frozenset(
    {
        "preflight-proven",
        "peer-mark-started",
        "recovery-lb-attested",
        "recovery-started",
        "recovery-both-nodes-drained",
        "rollback-restoring",
        "distinct-rollback-drained",
        "rollback-peer-admit",
        "rollback-node01-admit",
    }
)

FORWARD_COMMIT_LATER_HELPER_PHASES = frozenset(
    {
        "target-parity-proven",
        "peer-admit-started",
        "node01-admit-started",
        "commit-recovery-parity",
        "commit-peer-admit",
        "commit-node01-admit",
    }
)


def public_ready_wait_timeout_seconds(interval: int, threshold: int) -> int:
    if type(interval) is not int or interval < 1:
        raise SystemExit("LB health check interval is invalid")
    if type(threshold) is not int or threshold < 1:
        raise SystemExit("LB healthy threshold is invalid")
    return interval * threshold + PUBLIC_READY_HEALTH_SLACK_SECONDS


def load_lb_health_window(health: Any) -> tuple[int, int, int]:
    if not isinstance(health, dict):
        raise SystemExit("LB health contract is invalid")
    raw_interval = health.get("check_interval_seconds")
    raw_threshold = health.get("healthy_threshold")
    if not isinstance(raw_interval, int) or isinstance(raw_interval, bool):
        raise SystemExit("LB health check interval is invalid")
    if not isinstance(raw_threshold, int) or isinstance(raw_threshold, bool):
        raise SystemExit("LB healthy threshold is invalid")
    interval = raw_interval
    threshold = raw_threshold
    timeout = public_ready_wait_timeout_seconds(interval, threshold)
    return interval, threshold, timeout


def public_ready_probe_succeeded(status: Any, payload: Any) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    return payload.get("ok") is True


def wait_for_consecutive_public_ready(
    *,
    probe: Callable[[], bool],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    interval: int,
    threshold: int,
) -> None:
    timeout = public_ready_wait_timeout_seconds(interval, threshold)
    started = monotonic()
    consecutive = 0
    while True:
        if probe():
            consecutive += 1
            if consecutive >= threshold:
                return
        else:
            consecutive = 0
        remaining = timeout - (monotonic() - started)
        if remaining < interval:
            raise SystemExit("public load-balancer readiness did not become healthy within the LB health window")
        sleep(interval)


def authorize_later_dispatch_helper(
    *,
    phase: str,
    decision: str,
    journal_target: str,
    expected_target: str,
    blob_in_target_history: bool,
) -> str:
    if journal_target != expected_target:
        raise SystemExit("later helper target differs from the durable journal")
    if phase in PRE_MUTATION_LATER_HELPER_PHASES:
        return "pre-mutation"
    if phase in FORWARD_COMMIT_LATER_HELPER_PHASES:
        if decision != "commit":
            raise SystemExit("forward-only later helper requires a durable commit decision")
        if blob_in_target_history:
            raise SystemExit("running helper is a historical blob, not a later dispatch helper")
        return "forward-commit"
    if phase == "complete":
        raise SystemExit("later helper cannot reopen a terminal journal")
    raise SystemExit("running helper is not the exact authorized target blob")
