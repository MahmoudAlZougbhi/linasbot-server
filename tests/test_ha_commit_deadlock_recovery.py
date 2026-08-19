"""Regression locks for commit-deadlock public-ready wait and later-helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha import do_lb_ready_contract as lb_contract
from scripts.ha import public_ready_lb_wait_contract as wait_contract

LB_HEALTH_CONTRACT = lb_contract.LB_HEALTH_CONTRACT
FORWARD_COMMIT_LATER_HELPER_PHASES = wait_contract.FORWARD_COMMIT_LATER_HELPER_PHASES
PRE_MUTATION_LATER_HELPER_PHASES = wait_contract.PRE_MUTATION_LATER_HELPER_PHASES
PUBLIC_READY_HEALTH_SLACK_SECONDS = wait_contract.PUBLIC_READY_HEALTH_SLACK_SECONDS
PUBLIC_READY_URL = wait_contract.PUBLIC_READY_URL
authorize_later_dispatch_helper = wait_contract.authorize_later_dispatch_helper
load_lb_health_window = wait_contract.load_lb_health_window
public_ready_probe_succeeded = wait_contract.public_ready_probe_succeeded
wait_for_consecutive_public_ready = wait_contract.wait_for_consecutive_public_ready

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

TARGET = "4098b747cdd658d6ff89d2ea9b24fc5c3a85a885"
OTHER = "bca167fcd2f08fa1b1bc461226fffb42febb31e5"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _clock(steps: list[float]) -> tuple[object, object]:
    now = {"t": 0.0}

    def monotonic() -> float:
        return now["t"]

    def sleep(seconds: float) -> None:
        steps.append(seconds)
        now["t"] += seconds

    return monotonic, sleep


def test_lb_window_is_interval_5_threshold_2() -> None:
    interval, threshold, timeout = load_lb_health_window(LB_HEALTH_CONTRACT)
    assert interval == 5
    assert threshold == 2
    assert PUBLIC_READY_HEALTH_SLACK_SECONDS == 10
    assert timeout == 20
    assert timeout >= interval * threshold


def test_first_503_after_local_admit_is_not_success() -> None:
    assert public_ready_probe_succeeded(503, {"ok": False}) is False
    assert public_ready_probe_succeeded(503, "no healthy backends") is False
    assert public_ready_probe_succeeded(200, {"ok": True}) is True


def test_two_consecutive_200s_are_required() -> None:
    probes = [True]
    steps: list[float] = []
    monotonic, sleep = _clock(steps)
    with pytest.raises(SystemExit, match="LB health window"):
        wait_for_consecutive_public_ready(
            probe=lambda: probes.pop(0) if probes else False,
            monotonic=monotonic,
            sleep=sleep,
            interval=5,
            threshold=2,
        )
    probes = [True, True]
    steps.clear()
    wait_for_consecutive_public_ready(
        probe=lambda: probes.pop(0),
        monotonic=monotonic,
        sleep=sleep,
        interval=5,
        threshold=2,
    )
    assert steps == [5]


def test_200_then_503_resets_consecutive_counter() -> None:
    results = [True, False, True, True]
    steps: list[float] = []
    monotonic, sleep = _clock(steps)
    wait_for_consecutive_public_ready(
        probe=lambda: results.pop(0),
        monotonic=monotonic,
        sleep=sleep,
        interval=5,
        threshold=2,
    )
    assert steps == [5, 5, 5]


def test_timeout_stays_fail_closed() -> None:
    steps: list[float] = []
    monotonic, sleep = _clock(steps)
    with pytest.raises(SystemExit, match="LB health window"):
        wait_for_consecutive_public_ready(
            probe=lambda: False,
            monotonic=monotonic,
            sleep=sleep,
            interval=5,
            threshold=2,
        )
    assert steps == [5, 5, 5, 5]


@pytest.mark.parametrize("phase", sorted(FORWARD_COMMIT_LATER_HELPER_PHASES))
def test_later_helper_allowed_only_on_forward_commit_phases(phase: str) -> None:
    assert (
        authorize_later_dispatch_helper(
            phase=phase,
            decision="commit",
            journal_target=TARGET,
            expected_target=TARGET,
            blob_in_target_history=False,
        )
        == "forward-commit"
    )


@pytest.mark.parametrize(
    "phase",
    (
        "preflight-proven",
        "target-parity-awaiting-fresh-lb",
        "commit-lb-attested",
        "complete",
        "recovery-both-nodes-drained",
    ),
)
def test_later_helper_rejected_outside_forward_commit_exception(phase: str) -> None:
    if phase in PRE_MUTATION_LATER_HELPER_PHASES:
        assert (
            authorize_later_dispatch_helper(
                phase=phase,
                decision="rollback",
                journal_target=TARGET,
                expected_target=TARGET,
                blob_in_target_history=True,
            )
            == "pre-mutation"
        )
        return
    with pytest.raises(SystemExit, match="authorized target blob|terminal journal"):
        authorize_later_dispatch_helper(
            phase=phase,
            decision="commit",
            journal_target=TARGET,
            expected_target=TARGET,
            blob_in_target_history=False,
        )


def test_later_helper_rejected_when_decision_is_not_commit() -> None:
    with pytest.raises(SystemExit, match="durable commit decision"):
        authorize_later_dispatch_helper(
            phase="commit-peer-admit",
            decision="rollback",
            journal_target=TARGET,
            expected_target=TARGET,
            blob_in_target_history=False,
        )


def test_later_helper_rejected_on_target_or_journal_mismatch() -> None:
    with pytest.raises(SystemExit, match="differs from the durable journal"):
        authorize_later_dispatch_helper(
            phase="commit-peer-admit",
            decision="commit",
            journal_target=TARGET,
            expected_target=OTHER,
            blob_in_target_history=False,
        )
    with pytest.raises(SystemExit, match="historical blob"):
        authorize_later_dispatch_helper(
            phase="commit-peer-admit",
            decision="commit",
            journal_target=TARGET,
            expected_target=TARGET,
            blob_in_target_history=True,
        )


def test_public_readiness_gate_remains_mandatory() -> None:
    source = _helper()
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    commit = source[source.index("commit_target_deployment() {") : source.index("orchestrate() {")]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "assert_public_ready_after_peer_admission" in recover
    assert "assert_public_ready_after_peer_admission" in commit
    recover_admit = recover.index('remote_node "$peer_host" recover-admit "$target_sha" "$tx_dir"')
    recover_ready = recover.index('assert_public_ready_after_peer_admission "$target_sha"', recover_admit)
    recover_node01 = recover.index('node_recover_admit "$target_sha" "$tx_dir"', recover_ready)
    assert recover_admit < recover_ready < recover_node01
    commit_admit = commit.index('remote_node "$peer_host" recover-admit "$target_sha" "$tx_dir"')
    commit_ready = commit.index('assert_public_ready_after_peer_admission "$target_sha"', commit_admit)
    commit_node01 = commit.index('node_recover_admit "$target_sha" "$tx_dir"', commit_ready)
    assert commit_admit < commit_ready < commit_node01
    assert '    assert_public_ready\n    update_recovery_journal "rollback-node01-admit"' in recover
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "I_UNDERSTAND_SKIPPING_GATES" not in workflow
    assert "member.mode != 0o755" in workflow
    assert "check_interval_seconds" in source
    assert "healthy_threshold" in source
    assert PUBLIC_READY_URL in source
    assert "check_interval_seconds * healthy_threshold" in source or (
        "interval * threshold" in source and "slack = 10" in source
    )
    assert "DigitalOcean" in source or "LB health" in source
    assert 'update_recovery_journal "complete"' in recover
    assert "durable deployment commit decision cannot be reversed" in source


def test_helper_embeds_lb_window_and_forward_commit_later_helper() -> None:
    source = _helper()
    later = source[source.index("assert_later_dispatch_helper() {") : source.index("assert_public_ready() {")]
    wait = source[
        source.index("assert_public_ready_after_peer_admission() {") : source.index("assert_maintenance_readiness() {")
    ]
    recover = source[source.index("recover_deployment() {") : source.index("retry_distinct_reconciliation() {")]
    installer = source[
        source.index("install_lb_ready_attestation() {") : source.index("assert_lb_observation_strictly_newer() {")
    ]
    pre_mutation = "|".join(
        (
            "preflight-proven",
            "peer-mark-started",
            "recovery-lb-attested",
            "recovery-started",
            "recovery-both-nodes-drained",
            "rollback-restoring",
            "distinct-rollback-drained",
            "rollback-peer-admit",
            "rollback-node01-admit",
        )
    )
    forward = "|".join(
        (
            "target-parity-proven",
            "peer-admit-started",
            "node01-admit-started",
            "commit-recovery-parity",
            "commit-peer-admit",
            "commit-node01-admit",
        )
    )
    assert pre_mutation in later
    assert forward in later
    assert 'test "$decision" = commit' in later
    assert "historical blob, not a later dispatch helper" in later
    assert "cannot reopen a terminal journal" in later
    assert "assert_later_dispatch_helper" in recover
    assert "assert_later_dispatch_helper" in installer
    assert "later exact blob than the open pre-mutation journal" in later
    assert 'payload.get("ok") is True' in wait
    assert "status != 200" in wait or "response.status != 200" in wait
    assert "materialize_lb_manager" in wait
    assert "check_interval_seconds" in wait
    assert "healthy_threshold" in wait
    assert "slack = 10" in wait
    assert "consecutive = 0" in wait
    assert PUBLIC_READY_URL in wait
    assert "assert_public_ready_after_peer_admission" not in source[source.index("orchestrate() {") :]
    assert source[source.index("orchestrate() {") :].count("assert_public_ready") >= 1
