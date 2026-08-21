"""Recover must keep one LB observation through the authorized drain wait."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.ha.lb_attestation_window_contract import (
    ALREADY_DRAINED_RECOVERY_PHASES,
    MAX_DRAIN_SECONDS,
    MIN_DRAIN_SECONDS,
    OPERATOR_FRESHNESS_SECONDS,
    attestation_within_window,
    mutation_window_seconds,
    parse_observed_at,
    skip_extra_drain_wait,
    validate_drain_seconds,
)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _recover() -> str:
    source = _helper()
    return source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]


def test_mutation_window_is_operator_freshness_plus_drain() -> None:
    assert mutation_window_seconds(30) == 330
    assert mutation_window_seconds(240) == 540
    assert mutation_window_seconds(300) == 600
    assert validate_drain_seconds(45) == 45


@pytest.mark.parametrize("drain", (29, 301, True))
def test_invalid_drain_stays_fail_closed(drain: object) -> None:
    with pytest.raises(SystemExit, match="drain interval"):
        mutation_window_seconds(drain)  # type: ignore[arg-type]


def test_dispatch_window_rejects_age_over_five_minutes() -> None:
    now = datetime(2026, 8, 20, 18, 46, 43, tzinfo=UTC)
    observed = now - timedelta(seconds=318)
    assert (
        attestation_within_window(
            observed_at=observed,
            now=now,
            max_age_seconds=OPERATOR_FRESHNESS_SECONDS,
        )
        is False
    )
    assert (
        attestation_within_window(
            observed_at=observed,
            now=now,
            max_age_seconds=mutation_window_seconds(240),
        )
        is True
    )


def test_same_observation_is_required_after_drain() -> None:
    raw = "2026-08-20T18:41:25.431539Z"
    observed = parse_observed_at(raw)
    later = parse_observed_at("2026-08-20T18:46:43.400018Z")
    assert later - observed == timedelta(seconds=17, microseconds=968479) + timedelta(minutes=5)
    assert skip_extra_drain_wait("rollback-restoring") is True
    assert skip_extra_drain_wait("recovery-started") is False
    assert skip_extra_drain_wait("automatic-rollback-both-nodes-drained") is True
    assert "rollback-restoring" in ALREADY_DRAINED_RECOVERY_PHASES


def test_helper_extends_post_drain_window_and_skips_repeat_drain() -> None:
    recover = _recover()
    freshness = _helper()
    freshness = freshness[
        freshness.index("assert_fresh_lb_ready_attestation() {") : freshness.index(
            "lb_attestation_install_confirmation() {"
        )
    ]
    assert 'local max_age="${5:-300}"' in freshness
    assert "timedelta(seconds=max_age)" in freshness
    assert recover.count("$((300 + drain_seconds))") == 2
    assert "expired before rollback admission" in recover
    assert "expired before commit admission" in recover
    assert "skipping extra LB drain wait" in recover
    for phase in sorted(ALREADY_DRAINED_RECOVERY_PHASES):
        assert phase in recover
    assert MIN_DRAIN_SECONDS == 30
    assert MAX_DRAIN_SECONDS == 300
    sleep_idx = recover.index('sleep "$drain_seconds"')
    skip_idx = recover.index("skipping extra LB drain wait")
    assert skip_idx < sleep_idx
    rollback = recover.index("expired before rollback admission")
    window = recover.index("$((300 + drain_seconds))", recover.index("rollback-restoring"))
    assert window < rollback


def test_recover_commit_rechecks_fresh_lb_after_qg_verify_before_peer_admit() -> None:
    recover = _recover()
    commit = recover[
        recover.index('update_recovery_journal "commit-recovery-parity"') : recover.index(
            'update_recovery_journal "rollback-restoring"'
        )
    ]
    local_qg = commit.index("verify_staged_qg_payloads_after_restore")
    peer_qg = commit.index('remote_node "$peer_host" verify-staged-qg-payloads', local_qg)
    fresh_lb = commit.index("expired before commit admission", peer_qg)
    admit = commit.index('update_recovery_journal "commit-peer-admit"', fresh_lb)
    assert local_qg < peer_qg < fresh_lb < admit
    assert admit < commit.index('remote_node "$peer_host" recover-admit', admit)
    assert "expired before commit admission" not in commit[:local_qg]
